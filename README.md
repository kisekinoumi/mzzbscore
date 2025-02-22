

pyinstaller --onefile --add-data "ffi.dll;." --add-data "libcrypto-3-x64.dll;." --add-data "libssl-3-x64.dll;."  main.py
