# The map interface is FVED's main entry point, so the bare hostname sends
# visitors to it. 302, not 301: browsers cache a 301, and if the app later moves
# onto the bare hostname, a cached redirect would loop.
apiVersion: projectcontour.io/v1
kind: HTTPProxy
metadata:
  name: apex-redirect-httpproxy
  namespace: ${environment.namespace}
spec:
  virtualhost:
    fqdn: ${var.hostname}
    tls:
      secretName: ${var.hostname}-tls
  routes:
  - conditions:
    - prefix: /
    requestRedirectPolicy:
      scheme: https
      hostname: dashboards.${var.hostname}
      statusCode: 302
