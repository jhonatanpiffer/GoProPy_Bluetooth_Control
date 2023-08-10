import socket
import sys
import json
import argparse

SOCKET_FILE = './gopro.unix'

def escrever_no_socket_unix(args):
    command = args.command
    identifier = args.identifier
    obj_command = {
        "command": command,
        "identifier": identifier
    }

    str_command = json.dumps(obj_command)
    
    try:
        # Cria um objeto socket UNIX
        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        
        # Conecta ao socket UNIX
        unix_socket.connect(SOCKET_FILE)
        
        # Envia dados para o socket
        unix_socket.send(str_command.encode('utf-8'))

        # Lê dados do client_socket
        dados_recebidos = unix_socket.recv(1024)
        obj = json.loads(dados_recebidos.decode('utf-8'))
        if dados_recebidos:
            resp = {
                    "status": obj['status'],
                    "data": obj['data'],
                    "msg": obj['msg']
                    }
            print(json.dumps(resp))
        else:
            print("Erro na execução do comando")
        
    except Exception as e:
        print("Ocorreu um erro:", str(e))
        
    finally:
        unix_socket.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Connect to a GoPro camera, pair, then enable notifications.")
    parser.add_argument(
        "-i",
        "--identifier",
        type=str,
        help="Ultimos 4 digitos do numero serial da GoPro. Que são os ultimos 4 digitos do SSID da camera",
        default=None,
    )
    parser.add_argument(
        "-c",
        "--command",
        type=str,
        help="Comando para que o Daemon de comunicação bluetooth execute. Exemplo: scan, start, stop, connect_to {device_id}",
        default=None,
    )
    args = parser.parse_args()

    try:
        escrever_no_socket_unix(args)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(e)
        sys.exit(-1)
    else:
        sys.exit(0)

