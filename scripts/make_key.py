"""Print a new Fernet key for encryption at rest (ST_ENCRYPTION_KEY)."""
from cryptography.fernet import Fernet

print(Fernet.generate_key().decode())
