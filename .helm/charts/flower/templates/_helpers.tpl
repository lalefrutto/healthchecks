{{- define "flower.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "flower.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "flower.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "flower.labels" -}}
helm.sh/chart: {{ include "flower.chart" . }}
{{ include "flower.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: healthchecks
app.kubernetes.io/component: flower
{{- end }}

{{- define "flower.selectorLabels" -}}
app.kubernetes.io/name: {{ include "flower.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Имя ресурсов родительского чарта healthchecks — та же логика, что в его
"healthchecks.fullname" (release name, если содержит "healthchecks").
*/}}
{{- define "flower.appFullname" -}}
{{- if contains "healthchecks" .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-healthchecks" .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Образ: под werf — global.werf.image.healthchecks (werf кладёт service values и
в global), иначе global.image.repository:tag.
*/}}
{{- define "flower.image" -}}
{{- if and .Values.global.werf .Values.global.werf.image .Values.global.werf.image.healthchecks }}
{{- .Values.global.werf.image.healthchecks }}
{{- else }}
{{- printf "%s:%s" .Values.global.image.repository .Values.global.image.tag }}
{{- end }}
{{- end }}

{{/*
Окружение приложения: ConfigMap + несколько Secret'ов (Django, Postgres,
RabbitMQ) — зеркало "healthchecks.env" родительского чарта.
*/}}
{{- define "flower.env" -}}
envFrom:
  - configMapRef:
      name: {{ default (include "flower.appFullname" .) .Values.global.app.configMapName }}
env:
  - name: SECRET_KEY
    valueFrom:
      secretKeyRef:
        name: {{ default (include "flower.appFullname" .) .Values.global.app.secretName }}
        key: SECRET_KEY
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: {{ default (printf "%s-postgresql" .Release.Name) .Values.global.app.postgresqlSecretName }}
        key: password
  - name: RABBITMQ_PASSWORD
    valueFrom:
      secretKeyRef:
        name: {{ .Values.global.rabbitmq.existingSecret }}
        key: {{ .Values.global.rabbitmq.passwordKey }}
  - name: CELERY_BROKER_URL
    value: "amqp://$(RABBITMQ_USER):$(RABBITMQ_PASSWORD)@$(RABBITMQ_HOST):$(RABBITMQ_PORT)/$(RABBITMQ_VHOST)"
  {{- if .Values.global.redis.enabled }}
  - name: REDIS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: {{ .Values.global.redis.existingSecret }}
        key: {{ .Values.global.redis.passwordKey }}
  - name: REDIS_URL
    value: "redis://:$(REDIS_PASSWORD)@$(REDIS_HOST):$(REDIS_PORT)/$(REDIS_DB)"
  {{- end }}
  {{- if .Values.global.mongodb.enabled }}
  - name: MONGODB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: {{ .Values.global.mongodb.existingSecret }}
        key: {{ .Values.global.mongodb.passwordKey }}
  - name: MONGODB_URL
    value: "mongodb://$(MONGODB_USER):$(MONGODB_PASSWORD)@$(MONGODB_HOST):$(MONGODB_PORT)/$(MONGODB_DB)?authSource=$(MONGODB_DB)"
  {{- end }}
  {{- if .Values.global.s3.enabled }}
  - name: S3_ACCESS_KEY
    valueFrom:
      secretKeyRef:
        name: {{ default (printf "%s-s3" (include "flower.appFullname" .)) .Values.global.s3.existingSecret }}
        key: access_key
  - name: S3_SECRET_KEY
    valueFrom:
      secretKeyRef:
        name: {{ default (printf "%s-s3" (include "flower.appFullname" .)) .Values.global.s3.existingSecret }}
        key: secret_key
  {{- end }}
{{- end }}

{{- define "flower.secretName" -}}
{{- default (include "flower.fullname" .) .Values.existingSecret }}
{{- end }}
