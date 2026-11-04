FROM golang:1.26.8-alpine AS build
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /testhttp ./cmd/app

FROM scratch
COPY --from=build --chmod=0555 /testhttp /testhttp
USER 10001:0
EXPOSE 8080
ENTRYPOINT ["/testhttp"]
