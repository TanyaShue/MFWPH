from maa.controller import Controller, AdbController
from maa.define import MaaAdbInputMethodEnum
from maa.toolkit import Toolkit

# print(Toolkit.find_adb_devices())

adb=AdbController(adb_path="D:/leidian/LDPlayer9/adb.exe", address='127.0.0.1:5555',
               input_methods=MaaAdbInputMethodEnum.Maatouch,config={})
adb.post_connection().wait()
print(adb.connected)