"""
Génère les certificats TLS nécessaires à l'authentification mutuelle MQTT.

Produit dans ./certs/ :
    ca.key / ca.crt       — Autorité de certification interne
    server.key / server.crt — Certificat du broker Mosquitto
    client.key / client.crt — Certificat du client VaultCall

Usage :
    python generate_certs.py

Configuration Mosquitto (mosquitto.conf) à ajouter :
    listener 8883
    cafile   certs/ca.crt
    certfile certs/server.crt
    keyfile  certs/server.key
    require_certificate true
    tls_version tlsv1.2
"""

import datetime
import ipaddress
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERTS_DIR = os.path.join(os.path.dirname(__file__), "certs")
os.makedirs(CERTS_DIR, exist_ok=True)


def _rsa_key(bits: int = 2048):
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


def _save_key(key, path: str):
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    with open(path, "wb") as f:
        f.write(pem)
    print(f"  clé  → {path}")


def _save_cert(cert, path: str):
    with open(path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print(f"  cert → {path}")


def _name(cn: str) -> x509.Name:
    return x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "DZ"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "USTHB VaultCall"),
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
    ])


def generate_ca():
    print("\n[1/3] CA interne...")
    key = _rsa_key(4096)
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name("VaultCall Root CA"))
        .issuer_name(_name("VaultCall Root CA"))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    _save_key(key,  os.path.join(CERTS_DIR, "ca.key"))
    _save_cert(cert, os.path.join(CERTS_DIR, "ca.crt"))
    return key, cert


def generate_signed(ca_key, ca_cert, cn: str, is_server: bool = False):
    key = _rsa_key(2048)
    now = datetime.datetime.utcnow()
    builder = (
        x509.CertificateBuilder()
        .subject_name(_name(cn))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
    )
    if is_server:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
    cert = builder.sign(ca_key, hashes.SHA256())
    return key, cert


def main():
    print("=" * 55)
    print("  VaultCall — Génération des certificats TLS (mTLS)")
    print("=" * 55)

    ca_key, ca_cert = generate_ca()

    print("\n[2/3] Certificat serveur (broker Mosquitto)...")
    srv_key, srv_cert = generate_signed(ca_key, ca_cert, "localhost", is_server=True)
    _save_key(srv_key,  os.path.join(CERTS_DIR, "server.key"))
    _save_cert(srv_cert, os.path.join(CERTS_DIR, "server.crt"))

    print("\n[3/3] Certificat client (VaultCall)...")
    cli_key, cli_cert = generate_signed(ca_key, ca_cert, "vaultcall-client")
    _save_key(cli_key,  os.path.join(CERTS_DIR, "client.key"))
    _save_cert(cli_cert, os.path.join(CERTS_DIR, "client.crt"))

    print("\n✓ Certificats générés dans ./certs/")
    print("  Configurez Mosquitto avec mosquitto.conf fourni.")


if __name__ == "__main__":
    main()
