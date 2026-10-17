"""Lav et VAPID-nøglepar til web push (chauffør-notifikationer).

Brug:  docker run --rm containerflow:test python /app/scripts/gen-vapid.py
       (eller: python3 scripts/gen-vapid.py, hvis 'cryptography' er installeret)

Kopiér de to linjer ind som secrets (Scaleway: Container > Environment):
  VAPID_PUBLIC_KEY   (offentlig - sendes til browseren)
  VAPID_PRIVATE_KEY  (hemmelig - må ALDRIG i git)
Skift ikke nøglerne bagefter uden grund: alle chaufførers abonnementer er
knyttet til den offentlige nøgle og skal oprettes igen ved skift.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

key = ec.generate_private_key(ec.SECP256R1())
pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption()).decode()
pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
print("VAPID_PUBLIC_KEY=" + base64.urlsafe_b64encode(pub).decode().rstrip("="))
print("VAPID_PRIVATE_KEY=" + pem.strip().replace("\n", "\\n"))
