# testhttp

Простой HTTP-сервер на Go: `GET /` возвращает `hello world` и перевод строки
с типом `text/plain; charset=utf-8`. Другие пути возвращают 404, POST / — 405.
Go также обслуживает HEAD / без тела ответа.

## Локальный запуск

Нужен Go 1.26.8 или новее. Из корня проекта:

```powershell
go run ./cmd/app
```

Открой http://localhost:8080/ в браузере. Остановка — Ctrl+C.
Порт задаётся через `HTTP_PORT`, по умолчанию 8080. Файл `.env` необязателен;
готовый пример — `.env.example`. Переменные окружения имеют приоритет над `.env`.

```powershell
$env:HTTP_PORT = "9090"
go run ./cmd/app
```

Сервер слушает все интерфейсы, пишет логи в стандартный поток ошибок и при SIGTERM
или Ctrl+C ждёт завершения текущих запросов до 25 секунд. Ошибка запуска,
например занятый порт, завершает процесс с ненулевым кодом.

## Проверка

```powershell
go test ./...
go vet ./...
```

## Контейнер

Нужен запущенный Docker Engine:

```powershell
docker build -t testhttp:local .
docker run --rm -p 8080:8080 testhttp:local
```

Многоэтапная сборка создаёт статический Linux-бинарник. Финальный образ `scratch`
содержит только приложение, работает без root и поддерживает произвольный UID OKD.
Приложение не записывает файлы. `.env` и Git/IDE-файлы исключены из контекста сборки.

## Развёртывание в OKD

Нужны `oc`, вход в кластер и выбранный проект. Образ должен быть опубликован
в реестре, доступном узлам кластера. Для закрытого реестра заранее настрой
image pull secret в проекте. Команды ниже приведены для PowerShell.

1. Замени адрес реестра и имя пользователя на свои, затем собери и отправь образ:

   ```powershell
   $image = "quay.io/YOUR_USER/testhttp:v1"
   docker login quay.io
   docker build -t $image .
   docker push $image
   ```

2. В `deploy/okd.yaml` замени `image: testhttp:local` на полный адрес опубликованного
   образа (значение `$image`). Используй новый тег для каждой новой версии.

3. Выбери существующий проект и примени манифест:

   ```powershell
   oc project YOUR_PROJECT
   oc apply -f deploy/okd.yaml
   oc rollout status deployment/testhttp --timeout=120s
   oc get pods -l app=testhttp
   oc get route testhttp
   ```

4. Открой HTTPS-адрес из колонки HOST/PORT. Route использует сертификат ingress
   кластера: если CA внутренний, браузеру потребуется доверие к нему.

Манифест создаёт Deployment, Service и HTTPS Route с перенаправлением с HTTP.
Readiness и liveness проверяют существующую ручку `/`. UID не закреплён в
Deployment, чтобы OKD назначал его по политике проекта; расширение SCC не нужно.
Корневая файловая система доступна только для чтения, capabilities сброшены,
токен ServiceAccount не монтируется. HTTP внутри Pod работает на порту 8080.

## Структура

- `cmd/app` — конфигурация, обработка сигналов и запуск приложения.
- `config` — чтение и проверка настроек.
- `internal/app` — HTTP-обработчик и жизненный цикл приложения.
- `pkg/httpserver` — HTTP-сервер, таймауты и корректная остановка.
- `deploy/okd.yaml` — ресурсы OKD.
