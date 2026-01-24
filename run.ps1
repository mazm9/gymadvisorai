$env:SSL_CERT_FILE = (py -c "import certifi; print(certifi.where())")
$env:REQUESTS_CA_BUNDLE = $env:SSL_CERT_FILE
py -m gymadvisorai.app $args
