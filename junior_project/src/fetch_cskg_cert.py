"""a one-time setup tool. Downloads the server's security certificate to a file so app.py can verify it instead of skipping the check.
"""
import os
import re
import socket
import ssl
from pathlib import Path
from urllib.parse import urlparse

import requests

ENDPOINT = os.getenv('CSKG_ENDPOINT', 'https://192.167.149.12:9001/sparql/')
OUT = Path(__file__).parent / 'data' / 'cskg-ca.pem'


def describe(cert):
    """Print who the certificate says it is, so a hostname mismatch is visible."""
    subject = {k: v for part in cert.get('subject', ()) for k, v in part}
    issuer = {k: v for part in cert.get('issuer', ()) for k, v in part}
    sans = [value for kind, value in cert.get('subjectAltName', ()) if kind in ('DNS', 'IP Address')]
    print(f"  subject CN : {subject.get('commonName', '(none)')}")
    print(f"  issuer  CN : {issuer.get('commonName', '(none)')}")
    print(f"  valid from : {cert.get('notBefore', '?')}  to  {cert.get('notAfter', '?')}")
    print(f"  SAN entries: {', '.join(sans) if sans else '(none)'}")
    if issuer == subject:
        print("  note       : self-signed (issuer == subject). Expected for an internal server.")
    return sans

def main():
    parsed = urlparse(ENDPOINT)
    host = parsed.hostname
    port = parsed.port or 443
    print(f"Connecting to {host}:{port} ...")

    probe = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    probe.check_hostname = False
    probe.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=20) as raw:
            with probe.wrap_socket(raw, server_hostname=host) as tls:
                der = tls.getpeercert(binary_form=True)
    except OSError as exc:
        raise SystemExit(
            f"\nCould not reach {host}:{port} -- {exc}\n"
            "You are probably off the university network. Connect to it (or its VPN) and retry."
        )

    pem = ssl.DER_cert_to_PEM_cert(der)
    OUT.parent.mkdir(parents=True, exist_ok = True)
    OUT.write_text(pem, encoding = "utf-8")
    print(f"\nSaved certificate to {OUT}") 

    trusted = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    trusted.check_hostname = False
    trusted.load_verify_locations(cafile=str(OUT))
    with socket.create_connection((host, port), timeout=20) as raw:
        with trusted.wrap_socket(raw, server_hostname=host) as tls:
            parsed_cert = tls.getpeercert()
    print("\nCertificate details:")
    sans = describe(parsed_cert)

    print("\nTesting a real SPARQL request with verification ON ...")
    query = 'SELECT ?s WHERE { ?s ?p ?o } LIMIT 1'

    try:
        response = requests.post(ENDPOINT, data={'query': query},
                                 headers={'Accept': 'application/sparql-results+json'},
                                 verify=str(OUT), timeout=(10, 60))
        response.raise_for_status()
        response.json()
    except requests.exceptions.SSLError as exc:
        ip = host if re.fullmatch(r'[\d.]+', host or '') else None
        print(f"\nVerification still failed: {exc}\n")
        if ip and ip not in sans:
            print(
                "Cause: the certificate does not list this IP address in its SAN entries,\n"
                "so Python rejects it even though the certificate itself is now trusted.\n\n"
                "Fix: ask whoever runs the server for its proper hostname, then use that\n"
                "instead of the raw IP, adding it to your hosts file if DNS does not resolve it:\n"
                f"  {ip}  cskg.internal            <- C:\\Windows\\System32\\drivers\\etc\\hosts\n"
                "  $env:CSKG_ENDPOINT = 'https://cskg.internal:9001/sparql/'"
            )
        raise SystemExit(1)
    except requests.RequestException as exc:
        raise SystemExit(f"\nThe endpoint did not answer the query: {exc}")

    print("SUCCESS -- the endpoint answered with verification enabled.\n")
    print("Now build the concept catalog, in this same terminal:\n")
    print(f"  $env:REQUESTS_CA_BUNDLE = '{OUT}'")
    print("  python src/app.py --refresh-index\n")


if __name__ == '__main__':
    main()








