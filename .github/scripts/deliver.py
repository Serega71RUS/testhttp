"""Deliver only trusted develop/main pushes; never execute for pull requests."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

REGISTRY = 'registry.apps.okd.lab.home.arpa'
INTERNAL_IMAGE = 'image-registry.openshift-image-registry.svc:5000/images/testhttp'
ARGO = 'https://argocd.apps.okd.lab.home.arpa'
INFRA = 'git@github.com:Serega71RUS/homelab-infra.git'


def mask(value):
    escaped = value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print('::add-mask::' + escaped, flush=True)


def request_json(url, body=None, headers=None):
    headers = dict(headers or {})
    if body is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, headers)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raise RuntimeError('Identity/secret request failed, HTTP ' + str(error.code)) from None


def fetch_vault_credentials(branch):
    vault = os.environ.get('VAULT_ADDR', '').rstrip('/')
    if vault != 'https://vault.apps.okd.lab.home.arpa':
        raise RuntimeError('Unexpected Vault address')
    url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
    url += ('&' if '?' in url else '?') + urllib.parse.urlencode({'audience':'vault'})
    jwt = request_json(url, headers={'Authorization':'Bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})['value']
    mask(jwt)
    login = request_json(vault+'/v1/auth/github/login', {'role':'testhttp-'+branch, 'jwt':jwt})
    token = login['auth']['client_token']
    mask(token)
    headers = {'X-Vault-Token':token}
    try:
        credentials = request_json(vault+'/v1/kv/data/ci/testhttp/shared', headers=headers)['data']['data']
        if branch == 'develop':
            credentials.update(request_json(vault+'/v1/kv/data/ci/testhttp/develop', headers=headers)['data']['data'])
        names = {'infra_ssh_key':'INFRA_SSH_KEY', 'argo_read_token':'ARGO_READ_TOKEN', 'registry_token':'REGISTRY_TOKEN'}
        for name, value in credentials.items():
            if name in names:
                mask(value)
                os.environ[names[name]] = value
    finally:
        request_json(vault+'/v1/auth/token/revoke-self', {}, headers)


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def output(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def require_promotion(release, source_tree):
    if release.get('sourceTree') != source_tree:
        raise RuntimeError('main differs from the code built in develop; merge develop first')
    if release.get('verified') is not True:
        raise RuntimeError('The develop release has not passed deployment verification')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', release.get('digest', '')):
        raise RuntimeError('The develop release has no valid immutable image digest')
    return INTERNAL_IMAGE + '@' + release['digest']


def argo_ready(application, image):
    status = application.get('status', {})
    return (status.get('sync', {}).get('status') == 'Synced'
            and status.get('health', {}).get('status') == 'Healthy'
            and image in status.get('summary', {}).get('images', []))


def wait_for_deployment(environment, image, token, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        request = urllib.request.Request(
            ARGO + '/api/v1/applications/testhttp-' + environment + '?refresh=normal',
            headers={'Authorization': 'Bearer ' + token})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                application = json.load(response)
            if argo_ready(application, image):
                with urllib.request.urlopen(
                        f'https://testhttp-{environment}.apps.okd.lab.home.arpa/', timeout=20) as response:
                    if response.status == 200 and response.read() == b'hello world\n':
                        print(environment + ': Argo Synced/Healthy, expected image, HTTPS response verified')
                        return
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise RuntimeError('Argo read token is missing, expired or lacks access') from None
            print('Waiting for Argo/application, HTTP', error.code)
        except (urllib.error.URLError, TimeoutError):
            print('Waiting for Argo/application connectivity')
        time.sleep(10)
    raise RuntimeError('Timed out waiting for the expected healthy deployment')


def save_manifest(folder, documents, environment, image, source_sha):
    folder.mkdir(parents=True, exist_ok=True)
    result = copy.deepcopy(documents)
    kinds = [obj.get('kind') for obj in result]
    if sorted(kinds) != ['Deployment', 'Route', 'Service']:
        raise RuntimeError('Expected exactly a Deployment, Service and Route')
    for obj in result:
        if obj['metadata']['name'] != 'testhttp':
            raise RuntimeError('Unexpected resource name')
        obj['metadata']['namespace'] = environment
        obj['metadata'].setdefault('annotations', {})['homelab/source-commit'] = source_sha
        if obj['kind'] == 'Deployment':
            containers = obj['spec']['template']['spec']['containers']
            if len(containers) != 1 or containers[0]['name'] != 'testhttp':
                raise RuntimeError('Unexpected application containers')
            containers[0]['image'] = image
            obj['spec']['template']['metadata'].setdefault('annotations', {})['homelab/source-commit'] = source_sha
        elif obj['kind'] == 'Route':
            obj['spec']['host'] = f'testhttp-{environment}.apps.okd.lab.home.arpa'
    (folder/'app.yaml').write_text(yaml.safe_dump_all(result, sort_keys=False))


def commit_and_push(repo, message, env):
    run(['git', '-C', str(repo), 'add', 'environments'], env=env)
    changed = subprocess.run(['git', '-C', str(repo), 'diff', '--cached', '--quiet'], env=env).returncode
    if changed == 0:
        return
    if changed != 1:
        raise RuntimeError('Could not inspect the staged GitOps change')
    run(['git', '-C', str(repo), '-c', 'user.name=homelab-ci', '-c',
         'user.email=homelab-ci@users.noreply.github.com', 'commit', '-m', message], env=env)
    # A concurrent human edit is deliberately rejected instead of force-pushing.
    run(['git', '-C', str(repo), 'push', 'origin', 'HEAD:main'], env=env)


def main():
    branch = os.environ.get('GITHUB_REF_NAME')
    if os.environ.get('GITHUB_REPOSITORY') != 'Serega71RUS/testhttp' or branch not in ('develop', 'main'):
        raise RuntimeError('Delivery is allowed only from this repository develop/main')
    if os.environ.get('GITHUB_EVENT_NAME') not in ('push', 'workflow_dispatch'):
        raise RuntimeError('Untrusted event type')
    fetch_vault_credentials(branch)
    required = ['INFRA_SSH_KEY', 'ARGO_READ_TOKEN'] + (['REGISTRY_TOKEN'] if branch == 'develop' else [])
    for name in required:
        if not os.environ.get(name):
            raise RuntimeError(name + ' must be configured in Vault')
    source_sha = output(['git', 'rev-parse', 'HEAD'])
    if source_sha != os.environ['GITHUB_SHA']:
        raise RuntimeError('Checkout does not match the triggering commit')
    source_tree = output(['git', 'rev-parse', 'HEAD^{tree}'])
    environment = 'develop' if branch == 'develop' else 'production'
    with tempfile.TemporaryDirectory(prefix='testhttp-delivery-') as temporary:
        temporary = Path(temporary)
        key = temporary/'infra-key'
        key.write_text(os.environ['INFRA_SSH_KEY'].rstrip()+'\n')
        key.chmod(0o600)
        with urllib.request.urlopen('https://api.github.com/meta', timeout=20) as response:
            github_keys = json.load(response)['ssh_keys']
        known_hosts = temporary/'known_hosts'
        known_hosts.write_text(''.join('github.com '+key+'\n' for key in github_keys))
        env = os.environ.copy()
        env['GIT_SSH_COMMAND'] = f'ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile={known_hosts}'
        env['DOCKER_CONFIG'] = str(temporary/'docker')
        infra = temporary/'infra'
        run(['git', 'clone', '--depth=1', INFRA, str(infra)], env=env)
        develop = infra/'environments/develop/testhttp'
        destination = infra/'environments'/environment/'testhttp'
        if branch == 'develop':
            builder = 'golang:1.26.8-alpine'
            # The Dockerfile stays unchanged. An existing local base can be used
            # when external registries are temporarily unreachable.
            if subprocess.run(['docker', 'image', 'inspect', builder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env).returncode:
                run(['docker', 'pull', builder], env=env)
            run(['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}',
                 '-v', str(Path.cwd())+':/src:ro', '-w', '/src', '-e', 'GOCACHE=/tmp/go-cache',
                 '-e', 'GOMODCACHE=/tmp/go-modules', builder, 'sh', '-ec',
                 'go test ./... && go vet ./...'], env=env)
            tag = REGISTRY+'/images/testhttp:git-'+source_sha
            run(['docker', 'build', '--provenance=false', '--label', 'org.opencontainers.image.revision='+source_sha, '-t', tag, '.'], env=env)
            run(['docker', 'login', REGISTRY, '-u', 'testhttp-pusher', '--password-stdin'],
                input=os.environ['REGISTRY_TOKEN'].encode(), env=env)
            run(['docker', 'push', tag], env=env)
            digests = json.loads(output(['docker', 'image', 'inspect', tag, '--format', '{{json .RepoDigests}}'], env=env))
            digest = next(item.split('@')[1] for item in digests if item.startswith(REGISTRY+'/images/testhttp@'))
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
                raise RuntimeError('Missing image digest after push')
            image = INTERNAL_IMAGE+'@'+digest
            documents = list(yaml.safe_load_all(Path('deploy/okd.yaml').read_text()))
            release = {'sourceRepository':'Serega71RUS/testhttp', 'sourceCommit':source_sha,
                       'sourceTree':source_tree, 'digest':digest, 'verified':False,
                       'buildRun':os.environ['GITHUB_RUN_ID']}
        else:
            release = json.loads((develop/'release.json').read_text())
            image = require_promotion(release, source_tree)
            wait_for_deployment('develop', image, os.environ['ARGO_READ_TOKEN'])
            documents = list(yaml.safe_load_all((develop/'app.yaml').read_text()))
            release = dict(release, productionCommit=source_sha)
        save_manifest(destination, documents, environment, image, release['sourceCommit'])
        (destination/'release.json').write_text(json.dumps(release, indent=2)+'\n')
        commit_and_push(infra, f'Deploy testhttp {environment}: {source_sha[:12]}', env)
        wait_for_deployment(environment, image, os.environ['ARGO_READ_TOKEN'])
        if branch == 'develop':
            release['verified'] = True
            (destination/'release.json').write_text(json.dumps(release, indent=2)+'\n')
            commit_and_push(infra, f'Verify testhttp develop: {source_sha[:12]}', env)
        summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary, 'a') as file:
                file.write(f'### testhttp {environment}\n\nImage: `{image}`\n\n'
                           f'https://testhttp-{environment}.apps.okd.lab.home.arpa/\n')


if __name__ == '__main__':
    main()
