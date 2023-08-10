import socket
import os
import re
import sys
import asyncio
import argparse
from typing import Dict, Any, List, Callable, Optional
import json

from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice as BleakDevice

GOPRO_BASE_UUID = "b5f9{}-aa8d-11e3-9046-0002a5d5c51b"

SOCKET_FILE = './gopro.unix'
#SOCKET_FILE = '/var/www/html/360Linux/360v2/GoPy/gopro.unix'

# Certifique-se de remover o arquivo de socket se já existir
if os.path.exists(SOCKET_FILE):
    os.remove(SOCKET_FILE)

# Cria um objeto socket UNIX
unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

class Message_Queue:
    handle: int
    data: bytes
    def __init__(self, h, d):
        self.handle = h
        self.data = d

class Daemon_Singleton:
    _instancia = None
    devices: Dict[str, BleakDevice] = {}
    paired: False
    connected_device: str
    client: BleakClient = {}
    queue = asyncio.Queue()

    async def notification_handler(self, handle: int, data: bytes) -> None:
        print(f'Received response at {handle}: {data.hex(":")}')

        # Notify the writer
        msg = Message_Queue(handle, data)
        await self.queue.put(msg)
    
    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
        return cls._instancia

async def scan(arg):
    dev_list = [];
    
    try:
        # Map of discovered devices indexed by name
        #devices: Dict[str, BleakDevice] = {}
        Daemon_Singleton().devices = {}

        # Scan for devices
        print("Scanning for bluetooth devices...")

        # Scan callback to also catch nonconnectable scan responses
        # pylint: disable=cell-var-from-loop
        def _scan_callback(device: BleakDevice, _: Any) -> None:
            # Add to the dict if not unknown
            if device.name and device.name != "Unknown":
                Daemon_Singleton().devices[device.name] = device

        # Now get list of connectable advertisements
        for device in await BleakScanner.discover(timeout=3, detection_callback=_scan_callback):
            if device.name != "Unknown" and device.name is not None:
                Daemon_Singleton().devices[device.name] = device
        # Log every device we discovered
        for d in Daemon_Singleton().devices:
            dev_list.append(str(d))
            print(f"\tDiscovered: {d}")
            
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Connection establishment failed: {exc}")

    print("Scan concluido")
    resp = {
            "status": "ok",
            "data": dev_list,
            "msg": "Scan executado com sucesso"
    }
    return json.dumps(resp)

async def connect_to(identifier):

    if len(Daemon_Singleton().devices) < 1:
        resp = {
                "status": "Error",
                "data": f"{identifier}",
                "msg": "E necessario executar um scaneamento de dispositivos antes de tentar parear"
        }
        return json.dumps(resp)

    resp = {}

    token = re.compile(r"GoPro [A-Z0-9]{4}")
    if token.match(identifier):
        if identifier not in Daemon_Singleton().devices:
            Daemon_Singleton.paired = False
            Daemon_Singleton.connected_device = None
            resp = {
                    "status": "Error",
                    "data": f"{identifier}",
                    "msg": "Não tive visibilidade deste dispositivo"
            }
            return json.dumps(resp)

        device = Daemon_Singleton().devices[identifier]
        Daemon_Singleton().client = BleakClient(device)
        connect_result = await Daemon_Singleton().client.connect(timeout=15)
        if not connect_result:
            Daemon_Singleton.paired = False
            Daemon_Singleton.connected_device = None
            resp = {
                    "status": "Error",
                    "data": f"{identifier}",
                    "msg": "Não foi possivel connectar com a GoPro"
            }
            return json.dumps(resp)
        print("BLE Connected!", connect_result)

        # Try to pair (on some OS's this will expectedly fail)
        print("Attempting to pair...")
        try:
            pair_result = await Daemon_Singleton().client.pair()
            if not pair_result:
                Daemon_Singleton.paired = False
                Daemon_Singleton.connected_device = None
                resp = {
                        "status": "Error",
                        "data": f"{identifier}",
                        "msg": "Não foi possivel parear com a GoPro"
                }
                return json.dumps(resp)
        except NotImplementedError:
            # This is expected on Mac
            pass
        print("Pairing complete!", pair_result)
        Daemon_Singleton.paired = True
        Daemon_Singleton.connected_device = identifier
        resp = {
                "status": "Success",
                "data": f"{identifier}",
                "msg": "Dispositivo connectado e pareado com sucesso"
        }
    else:
        resp = {
                "status": "Error",
                "data": f"{identifier}",
                "msg": "Dispositivo não é uma GoPro"
        }

    # Enable notifications on all notifiable characteristics
    print("Enabling notifications...")
    for service in Daemon_Singleton().client.services:
        for char in service.characteristics:
            if "notify" in char.properties:
                print(f"Enabling notification on char {char.uuid}")
                await Daemon_Singleton().client.start_notify(char, Daemon_Singleton().notification_handler)  # type: ignore
    print("Done enabling notifications")

    return json.dumps(resp)

async def start(arg):
    resp = {}
    # UUIDs to write to and receive responses from
    COMMAND_REQ_UUID = GOPRO_BASE_UUID.format("0072")
    COMMAND_RSP_UUID = GOPRO_BASE_UUID.format("0073")
    response_uuid = COMMAND_RSP_UUID

    client = Daemon_Singleton().client


    # Write to command request BleUUID to turn the shutter on
    print("Setting the shutter on")
    await client.write_gatt_char(COMMAND_REQ_UUID, bytearray([3, 1, 1, 1]), response=True)
    message = await Daemon_Singleton().queue.get()  # Wait to receive the notification response
    
    # If this is the correct handle and the status is success, the command was a success
    if Daemon_Singleton().client.services.characteristics[message.handle].uuid == response_uuid and message.data[2] == 0x00:
        print("Command sent successfully")
        resp = {
                "status": "Success",
                #"data": message.data.decode('utf-8'),
                "data": "success",
                "msg": "Gravação iniciada"
        }
    # Anything else is unexpected. This shouldn't happen
    else:
        print("Unexpected response")
        resp = {
                "status": "Error",
                #"data": message.data.decode('utf-8'),
                "data": "Error",
                "msg": "Não foi possivel iniciar a gravação"
        }
    return json.dumps(resp)

async def stop(arg):
    resp = {}
    # UUIDs to write to and receive responses from
    COMMAND_REQ_UUID = GOPRO_BASE_UUID.format("0072")
    COMMAND_RSP_UUID = GOPRO_BASE_UUID.format("0073")
    response_uuid = COMMAND_RSP_UUID

    client = Daemon_Singleton().client


    # Write to command request BleUUID to turn the shutter off
    print("Setting the shutter off")
    await client.write_gatt_char(COMMAND_REQ_UUID, bytearray([3, 1, 1, 0]), response=True)
    message = await Daemon_Singleton().queue.get()  # Wait to receive the notification response
    
    # If this is the correct handle and the status is success, the command was a success
    if Daemon_Singleton().client.services.characteristics[message.handle].uuid == response_uuid and message.data[2] == 0x00:
        print("Command sent successfully")
        resp = {
                "status": "Success",
                #"data": message.data.decode('utf-8'),
                "data": "success",
                "msg": "Gravação iniciada"
        }
    # Anything else is unexpected. This shouldn't happen
    else:
        print("Unexpected response")
        resp = {
                "status": "Error",
                #"data": message.data.decode('utf-8'),
                "data": "Error",
                "msg": "Não foi possivel iniciar a gravação"
        }
    return json.dumps(resp)

# Dicionário de mapeamento de strings para funções
funcoes = {
    "scan": scan,
    "connect_to": connect_to,
    "start": start,
    "stop": stop
}

async def run_command(json_command):
    command = json_command['command']
    if command in funcoes:
      selected_command = funcoes[command]
      return await selected_command(json_command['identifier'])
    else:
        print("Comando Invalido")
        resp = {
                "status": "erro",
                "data": f"Comando: {command}. Invalido!",
                "msg": "Esse não é um comando valido. Consulte o manual ^^"
        }
        return json.dumps(resp)

async def main(identifier: Optional[str]) -> None:
  try:
      # Vincula o socket ao arquivo de socket
      unix_socket.bind(SOCKET_FILE)
      
      # Define o socket para ouvir conexões
      unix_socket.listen(5)
      
      print(f"Socket Unix criado em {SOCKET_FILE}. Aguardando conexões...")
      
      while True:
          # Aceita uma conexão de cliente
          client_socket, client_address = unix_socket.accept()
          print(f"Conexão aceita de {client_address}")
          
          # Lê dados do client_socket
          dados = client_socket.recv(1024)
          if not dados:
              print("Erro na leitura do comando")
              continue
          
          str_command = dados.decode('utf-8')
          json_command = json.loads(str_command)

          print(f"Comando recebido: {json_command['command']}")
  
          #logica do comando balabal
          result = await run_command(json_command)
  
          client_socket.send(result.encode('utf-8'))
          
          # Fecha o socket do cliente
          #client_socket.close()
          
  except Exception as e:
      print("Ocorreu um erro:", str(e))
  finally:
      # Fecha o socket Unix
      unix_socket.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Connect to a GoPro camera, pair, then enable notifications.")
    parser.add_argument(
        "-i",
        "--identifier",
        type=str,
        help="Last 4 digits of GoPro serial number, which is the last 4 digits of the default camera SSID. \
            If not used, first discovered GoPro will be connected to",
        default=None,
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.identifier))
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(e)
        sys.exit(-1)
    else:
        sys.exit(0)
