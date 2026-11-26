{{/* Shared helpers for the EIL API chart. */}}
{{- define "eil.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- define "eil.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- define "eil.labels" -}}
app.kubernetes.io/name: {{ include "eil.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
{{- define "eil.selectorLabels" -}}
app.kubernetes.io/name: {{ include "eil.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
{{- define "eil.serviceAccountName" -}}
{{- default "default" .Values.serviceAccount }}
{{- end }}
