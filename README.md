Este repositorio almacena mi colección de scripts, archivos y firmwares orientados a la modificación y control de la placa de desarrollo `ESP32 PLUS de Keystudio`, tratado en robótica de 1º de Bachillerato. 

# ESP32PLUS (Keystudio)
La ESP32 PLUS de Keyestudio es una de las placas de desarrollo que esta marca sacó como alternativa al Arduino UNO/Mega, pero con el chip ESP32 de Espressif en vez del ATmega. Además, brinda mayor rendimiento (240MHz a comparación con los 16MHz de Arduino UNO), memoria más amplia y conectividad inhalámbrica nativa:
- WIFI 802.11 b/g/n (solo 2.4GHz)
- BLUETOOTH
- 520kb de SRAM interna y 4MB FLASH

# ESP32 utilizada

### ESP32 PLUS de Keystudio (STEAMAKER based)
Originalmente diseñada para utilizar en steamakersblocks.com y programarla con bloques, sin embargo, al ser una ESP32 al fin y al cabo, es completamente reprogramable. Consta de las siguientes características (importante a la hora de flashear firmwares):
- FLASH de 4MB
- ~ 2.6MB de almacenamiento para sistema de archivos
- ~ 155Kb de RAM



# USO
Cada carpeta contiene su propio README, explicando el contenido de esta, su instalación y su uso. 
Está dividido en `PERSONAL` y `ROBÓTICA`, en función de si contiene scripts referentes a las tareas de robótica o al uso y experimentación personal. 

---
# :file_folder: CARPETAS

## /FIRMWARE
Contiene todos los binarios de instalación listos para instalar en la ESP32 PLUS, junto a una explicación de como flashearlo en cada caso utilizando la libreria `esptool` de python. En la carpeta de cada proyecto se incluye el binario que se usa respectivamente, pero esta carpeta los almacena de forma centralizada. 
> ⚠️ Dado que no es una placa de desarrollo muy utilizada, la mayoria de firmwares utilizados son binarios diseñados para ESP32 Genérica. Sin embargo, es importante verificar el almacenamiento máximo de flash de la placa utilizada, para evitar corromper la instalación. 
