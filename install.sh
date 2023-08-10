#!/bin/bash

echo "alias python='python3'" >>  ~/.bashrc

git clone https://github.com/jhonatanpiffer/GoProPy_Bluetooth_Control
cd GoProPy_Bluetooth_Control/

git clone https://github.com/gopro/OpenGoPro

#Comando para instalar dependencias da lib
cd GoProPy/OpenGoPro/demos/python/tutorial
pip install -e .
cd - 


pip install python-daemon
