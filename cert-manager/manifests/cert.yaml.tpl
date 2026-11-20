apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: ${var.hostname}-dashboards-cert
spec:
  commonName: dashboards.${var.hostname}
  dnsNames:
  - dashboards.${var.hostname}
  issuerRef:
    name: ${var.certificateIssuerName}
    kind: ClusterIssuer
  secretName: dashboards.${var.hostname}-tls
---
# The bare hostname redirects to the dashboards (ingress/manifests/apex-redirect.yaml.tpl).
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: ${var.hostname}-apex-cert
spec:
  commonName: ${var.hostname}
  dnsNames:
  - ${var.hostname}
  issuerRef:
    name: ${var.certificateIssuerName}
    kind: ClusterIssuer
  secretName: ${var.hostname}-tls
