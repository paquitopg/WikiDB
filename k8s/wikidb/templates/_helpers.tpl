{{- define "wikidb.labels" -}}
app.kubernetes.io/name: wikidb
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "wikidb.image" -}}
{{- if .Values.image.digest -}}
{{ .Values.image.repository }}@{{ .Values.image.digest }}
{{- else -}}
{{ .Values.image.repository }}:{{ required "image.tag or image.digest is required" .Values.image.tag }}
{{- end -}}
{{- end -}}

{{- define "wikidb.javaOpts" -}}
-Xmx{{ .Values.javaHeap }}
{{- with .Values.oidc }}
{{- if .proxyHost }} -Dhttps.proxyHost={{ .proxyHost }} -Dhttps.proxyPort={{ .proxyPort }} -Dhttp.nonProxyHosts={{ .nonProxyHosts | quote }}{{ end }}
{{- if .userAgent }} -Dhttp.agent={{ .userAgent | quote }}{{ end }}
{{- end }}
{{- end -}}
