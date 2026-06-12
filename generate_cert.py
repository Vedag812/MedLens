"""
Generate a self-signed SSL certificate for mobile testing.
Phone browsers require HTTPS to access the camera via getUserMedia.
Run this once, then start the server with --ssl-keyfile and --ssl-certfile.
"""

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime
import socket
import os


def get_local_ip():
    """Get the machine's local network IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def generate_cert():
    cert_dir = os.path.join(os.path.dirname(__file__), "certs")
    os.makedirs(cert_dir, exist_ok=True)

    key_path = os.path.join(cert_dir, "key.pem")
    cert_path = os.path.join(cert_dir, "cert.pem")

    local_ip = get_local_ip()
    print(f"Local IP: {local_ip}")

    # Generate private key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Build certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Dev"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MedLens"),
        x509.NameAttribute(NameOID.COMMON_NAME, "MedLens Dev Server"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress_from_str("127.0.0.1")),
                x509.IPAddress(ipaddress_from_str(local_ip)),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    # Write key
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    # Write cert
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Certificate generated at: {cert_path}")
    print(f"Key generated at: {key_path}")
    print(f"\nTo test on your phone:")
    print(f"  1. Connect phone to same WiFi as this computer")
    print(f"  2. Open: https://{local_ip}:8000")
    print(f"  3. Accept the security warning (it's a self-signed cert)")
    print(f"  4. The camera should work!")

    return key_path, cert_path


def ipaddress_from_str(ip_str):
    import ipaddress
    return ipaddress.ip_address(ip_str)


if __name__ == "__main__":
    generate_cert()
