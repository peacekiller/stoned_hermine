#!/usr/bin/env python3
import argparse
import base64
import http.client
import json
import logging
import uuid
import string
import random

import requests

try:
    import socketio
except ModuleNotFoundError:
    socketio = None

import Crypto.PublicKey.RSA
import Crypto.Cipher
import Crypto.Cipher.PKCS1_OAEP
import Crypto.Cipher.AES
import Crypto.Random
import Crypto.Util.Padding


class StashCatClient:
    base_url = "https://api.thw-messenger.de"
    push_url = "https://push.thw-messenger.de"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.5",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 ("
                      "KHTML, like Gecko) Chrome/97.0.4692.99 Mobile Safari/537.36",
    }

    private_key = None

    _key_cache = {}

    def __init__(self, device_id=None, client_key=None, user_id=None, hidden_id=None):
        if device_id is None:
            device_id = "".join(random.choice(string.ascii_letters + string.digits)
                                for _ in range(32))

        self.device_id = device_id
        self.client_key = client_key
        self.user_id = user_id
        self.hidden_id = hidden_id

    def _post(self, url, *, data, include_auth=True, **kwargs):
        data["device_id"] = self.device_id
        if include_auth:
            data["client_key"] = self.client_key

        response = requests.post(f"{self.base_url}/{url}", data=data, headers=self.headers,
                                 **kwargs)
        try:
            response.raise_for_status()
        except requests.RequestException as exception:
            raise ValueError(exception) from exception

        resp_data = response.json()
        if resp_data["status"]["value"] != "OK":
            raise ValueError(resp_data["status"]["message"])
        return resp_data["payload"]

    def login(self, username, password):
        data = self._post("auth/login", include_auth=False, data={
            "email": username,
            "password": password,
            "app_name": "hermine@thw-Chrome:97.0.4692.99-browser-4.11.1",
            "encrypted": True,
            "callable": True,
        })

        self.client_key = data["client_key"]
        self.user_id = data["userinfo"]["id"]
        self.hidden_id = data["userinfo"]["socket_id"]
        return data

    def get_socket(self):
        if socketio is None:
            raise NotImplementedError

        sio = socketio.Client()
        @sio.on("connect")
        def _connect():
            sio.emit("userid", {"hidden_id": self.hidden_id,
                                "device_id": self.device_id,
                                "client_key": self.client_key})

        sio.connect(self.push_url)
        return sio

    def check(self):
        data = self._post("auth/check", data={
            "app_name": "hermine@thw-Chrome:97.0.4692.99-browser-4.11.1",
            "encrypted": True,
            "callable": True,
        })

    def open_private_key(self, encryption_password):
        data = self._post("security/get_private_key", data={})
        private_key_field = json.loads(data["keys"]["private_key"])
        # there might be an unescaping bug here....
        self.private_key = Crypto.PublicKey.RSA.import_key(
            private_key_field["private"], passphrase=encryption_password
        )

    def get_open_conversations(self, *, limit=30, offset=0):
        data = self._post("message/conversations", data={
            "limit": limit,
            "offset": offset,
            "archive": 0,
        })
        return data["conversations"]

    def search_user(self, search, *, limit=50, offset=0):
        data = self._post("users/listing", data={
            "limit": limit,
            "offset": offset,
            "key_hashes": False,
            "search": search,
            "sorting": ["first_name_asc", "last_name_asc"],
            "exclude_user_ids": [],
            "group_ids": [],
        })
        return data["users"]

    def user_info(self, user_id):
        return self._post("users/info", data={"user_id": user_id, "withkey": True})["user"]

    def open_conversation(self, members):
        conversation_key = Crypto.Random.get_random_bytes(32)

        receivers = []
        # Always add ourselves
        encryptor = Crypto.Cipher.PKCS1_OAEP.new(self.private_key.publickey())
        receivers.append({
            "id": int(self.user_id),
            "key": base64.b64encode(encryptor.encrypt(conversation_key)).decode("utf-8")
        })
        for member in members:
            pubkey = Crypto.PublicKey.RSA.import_key(member["public_key"])
            encryptor = Crypto.Cipher.PKCS1_OAEP.new(pubkey)
            receivers.append({
                "id": int(member["id"]),
                "key": base64.b64encode(encryptor.encrypt(conversation_key)).decode("utf-8")
            })

        data = self._post("message/createEncryptedConversation", data={
            "members": json.dumps(receivers),
        })
        conversation = data["conversation"]
        self._key_cache[("conversation", conversation["id"])] = conversation["key"]
        return conversation

    def get_messages(self, source, limit=30, offset=0):
        data = self._post("message/content", data={
            f"{source[0]}_id": source[1],
            "source": source[0],
            "limit": limit,
            "offset": offset,
        })

        conversation_key = self._get_conversation_key(source)

        for message in data["messages"]:
            if message["kind"] == "message" and message["encrypted"]:
                if message["text"] is not None:
                    message["text_decrypted"] = _decrypt_aes(
                        bytes.fromhex(message["text"] ),
                        conversation_key,
                        bytes.fromhex(message["iv"])
                    ).decode("utf-8")

                if message["location"]["encrypted"]:
                    message["location"]["latitude_decrypted"] = _decrypt_aes(
                        bytes.fromhex(message["location"]["latitude"]),
                        conversation_key,
                        bytes.fromhex(message["location"]["iv"])
                    ).decode("utf-8")
                    message["location"]["longitude_decrypted"] = _decrypt_aes(
                        bytes.fromhex(message["location"]["longitude"]),
                        conversation_key,
                        bytes.fromhex(message["location"]["iv"])
                    ).decode("utf-8")
            yield message

    def get_companies(self):
        data = self._post("company/member", data={"no_cache": True})
        return data["companies"]

    def get_channels(self, company_id):
        data = self._post("channels/subscripted", data={"company": company_id})
        return data["channels"]

    def _get_conversation_key(self, target):
        try:
            encrypted_key = self._key_cache[target]
        except KeyError:
            if target[0] == "conversation":
                data = self._post("message/conversation",
                                  data={"conversation_id": target[1]})
                encrypted_key = data["conversation"]["key"]
            elif target[0] == "channel":
                data = self._post("channels/info", data={
                    "channel_id": target[1],
                    "without_members": True
                })
                encrypted_key = data["channels"]["key"]
            else:
                raise AttributeError from None

            self._key_cache[target] = encrypted_key

        decryptor = Crypto.Cipher.PKCS1_OAEP.new(self.private_key)
        return decryptor.decrypt(base64.b64decode(encrypted_key))

    def send_msg(self, target, message, *, files=None, location=None):
        files = files or []

        iv = Crypto.Random.get_random_bytes(16)
        conversation_key = self._get_conversation_key(target)

        payload = {
            "client_key": self.client_key,
            "device_id": self.device_id,
            "target": target[0],
            f"{target[0]}_id": target[1],
            "text": _encrypt_aes(message.encode("utf-8"), conversation_key, iv).hex(),
            "iv": iv.hex(),
            "files": json.dumps(files),
            "url": "[]",
            "type": "text",
            "verification": "",
            "encrypted": True,
            "metainfo": '{"v": 1, "style": "md"}'
        }

        if location:
            payload["latitude"] = _encrypt_aes(
                str(location[0]).encode("utf-8"), conversation_key, iv).hex()
            payload["longitude"] = _encrypt_aes(
                str(location[1]).encode("utf-8"), conversation_key, iv).hex()

        return self._post("message/send", data=payload)["message"]

    def send_msg_to_channel(self, channel_id, message):
        return self.send_msg(("channel", channel_id), message)

    def send_msg_to_user(self, conversation_id, message):
        return self.send_msg(("conversation", conversation_id), message)

    def upload_file(self, target, file, filename, content_type="application/octet-stream", *,
                    media_size=None):
        media_size = media_size or (None, None)
        # All chunks must share the same iv
        iv = Crypto.Random.get_random_bytes(16)
        file_key = Crypto.Random.get_random_bytes(32)

        content = file.read()
        chunk_size = 5 * 1024 * 1024
        upload_uuid = str(uuid.uuid4())
        for nr in range(-(len(content) // -chunk_size)):
            chunk = content[nr * chunk_size:(nr + 1) * chunk_size]
            ct_bytes = _encrypt_aes(
                chunk,
                file_key,
                iv
            )

            file_data = self._post("file/upload", data={
                "resumableChunkNumber": nr,
                "resumableChunkSize": chunk_size,
                "resumableCurrentChunkSize": len(ct_bytes),
                "resumableTotalSize": len(content),
                "resumableType": content_type,
                "resumableIdentifier": upload_uuid,
                "resumableFilename": filename,
                "resumableRelativePath": filename,
                "resumableTotalChunks": -(len(content) // -chunk_size),
                "folder": 0,
                "type": target[0],
                "type_id": target[1],
                "encrypted": True,
                "iv": iv.hex(),
                "media_width": media_size[0],
                "media_height": media_size[1],
            }, files={"file": ("[object Object]", ct_bytes, "application/octet-stream")})["file"]

        iv = Crypto.Random.get_random_bytes(16)
        self._post("security/set_file_access_key", data={
            "file_id": file_data["id"],
            "target": target[0],
            "target_id": target[1],
            "key": _encrypt_aes(file_key, self._get_conversation_key(target), iv).hex(),
            "iv": iv.hex(),
        })

        return file_data


def _encrypt_aes(plain: bytes, key: bytes, iv: bytes):
    return Crypto.Cipher.AES.new(key, Crypto.Cipher.AES.MODE_CBC, iv=iv).encrypt(
        Crypto.Util.Padding.pad(plain, Crypto.Cipher.AES.block_size)
    )


def _decrypt_aes(cipher: bytes, key: bytes, iv: bytes):
    if not cipher:
        return b''
    return Crypto.Util.Padding.unpad(
        Crypto.Cipher.AES.new(key, Crypto.Cipher.AES.MODE_CBC, iv=iv).decrypt(cipher),
        Crypto.Cipher.AES.block_size
    )
