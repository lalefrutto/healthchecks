{{/*
Expand the name of the chart.
*/}}
{{- define "healthchecks.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "healthchecks.fullname" -}}
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

{{/*
Chart label value.
*/}}
{{- define "healthchecks.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "healthchecks.labels" -}}
helm.sh/chart: {{ include "healthchecks.chart" . }}
{{ include "healthchecks.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: healthchecks
{{- end }}

{{/*
Selector labels (без component — его добавляет каждый workload сам).
*/}}
{{- define "healthchecks.selectorLabels" -}}
app.kubernetes.io/name: {{ include "healthchecks.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Имя secret'а с SECRET_KEY.
*/}}
{{- define "healthchecks.secretName" -}}
{{- default (include "healthchecks.fullname" .) .Values.secrets.existingSecret }}
{{- end }}

{{/*
Полное имя subchart'а postgresql — так же, как его считает сам subchart.
*/}}
{{- define "healthchecks.postgresql.fullname" -}}
{{- printf "%s-postgresql" .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "healthchecks.database.host" -}}
{{- if .Values.postgresql.enabled }}
{{- include "healthchecks.postgresql.fullname" . }}
{{- else }}
{{- required "externalDatabase.host is required when postgresql.enabled=false" .Values.externalDatabase.host }}
{{- end }}
{{- end }}

{{- define "healthchecks.database.port" -}}
{{- if .Values.postgresql.enabled }}5432{{ else }}{{ .Values.externalDatabase.port }}{{ end }}
{{- end }}

{{- define "healthchecks.database.name" -}}
{{- if .Values.postgresql.enabled }}{{ .Values.postgresql.auth.database }}{{ else }}{{ .Values.externalDatabase.database }}{{ end }}
{{- end }}

{{- define "healthchecks.database.user" -}}
{{- if .Values.postgresql.enabled }}{{ .Values.postgresql.auth.username }}{{ else }}{{ .Values.externalDatabase.username }}{{ end }}
{{- end }}

{{/*
Secret с паролем БД (ключ `password`).
*/}}
{{- define "healthchecks.database.secretName" -}}
{{- if .Values.postgresql.enabled }}
{{- default (include "healthchecks.postgresql.fullname" .) .Values.postgresql.auth.existingSecret }}
{{- else }}
{{- required "externalDatabase.existingSecret is required when postgresql.enabled=false" .Values.externalDatabase.existingSecret }}
{{- end }}
{{- end }}

{{/*
Общий блок окружения для всех контейнеров приложения.
*/}}
{{- define "healthchecks.env" -}}
envFrom:
  - configMapRef:
      name: {{ include "healthchecks.fullname" . }}
env:
  - name: SECRET_KEY
    valueFrom:
      secretKeyRef:
        name: {{ include "healthchecks.secretName" . }}
        key: SECRET_KEY
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: {{ include "healthchecks.database.secretName" . }}
        key: password
  {{- with .Values.extraEnv }}
  {{- toYaml . | nindent 2 }}
  {{- end }}
{{- end }}

{{/*
Init-контейнер, ждущий готовности Postgres.
*/}}
{{- define "healthchecks.waitForDb" -}}
{{- if .Values.waitForDb.enabled }}
initContainers:
  - name: wait-for-db
    image: {{ .Values.waitForDb.image }}
    envFrom:
      - configMapRef:
          name: {{ include "healthchecks.fullname" . }}
    command:
      - sh
      - -c
      - |
        until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
          echo "waiting for postgres at $DB_HOST:$DB_PORT..."
          sleep 2
        done
    resources:
      {{- toYaml .Values.waitForDb.resources | nindent 6 }}
{{- end }}
{{- end }}

{{/*
Образ приложения.
*/}}
{{- define "healthchecks.image" -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) }}
{{- end }}
