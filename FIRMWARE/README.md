# CONTENIDO

Esta carpeta contiene todos los binarios de los firmwares utilizados en cada proyecto respectivamente. 

Todos son compatibles con la placa de desarrollo `ESP32 PLUS`, exceptuando el binario de wifi marauder, que tiene diversos problemas en el sistema de archivos, lo que no permite mantener persistencia ni guardar progreso. 

---

# INSTALACIÓN

Para poder flashear los binarios, vamos a utilizar la libreria de python `esptool`, que permite manejar los firmwares en las placas ESP32. Se puede instalar en cualquier OS que permita Python:
``` 
pip install esptool
```
Siempre que flasheemos un firmware de imagen completa es recomendable borrar el firmware previo:
```
esptool --chip esp32 erase-flash
```

> En caso de tener más de una esp32 conectada al ordenador, siempre se debe especificar el puerto COM correspondiente añadiendo el parámetro `--com COMx` en el que `x` es el número de COM conectado.


---

# FIRMWARES

## MICROPYTHON_v1.26.1.bin
Contiene la imagen completa del firmware de micropython, instalable con:
```

```

---

## WLED_v0.16.0-alpha_v4.bin
Contiene la app de WLED, pero previamente necesitamos flashear `WLED_bootloader_v4.bin` para evitar bootloops:
```
esptool write_flash 0x0 WLED_bootloader_v4.bin
```
y luego ya podemos instalar WLED con:
```
esptool write_flash 0x10000 WLED_v0.16.0-alpha_v4.bin
```

