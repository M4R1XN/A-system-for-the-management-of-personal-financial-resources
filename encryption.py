from cryptography.fernet import Fernet

# Load or generate the encryption key (store it securely)
try:
    with open('secret.key', 'rb') as key_file:
        key = key_file.read()
except FileNotFoundError:
    key = Fernet.generate_key()
    with open('secret.key', 'wb') as key_file:
        key_file.write(key)

fernet = Fernet(key)

def fernet_encrypt(data):
    """Encrypt the data using Fernet encryption."""
    try:
        return fernet.encrypt(data.encode())
    except Exception as e:
        print(f"Encryption failed: {e}")
        return None

def fernet_decrypt(data):
    """Decrypt the data using Fernet encryption."""
    try:
        if isinstance(data, str):
            data = data.encode()
        return fernet.decrypt(data).decode()
    except Exception as e:
        print(f"Decryption failed: {e}")
        return None
