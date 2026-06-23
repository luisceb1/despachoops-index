\# DespachoOps — Expediente vivo



\## 1. Objetivo



Este módulo convierte el índice documental del despacho en una capa operativa de trabajo sobre clientes y expedientes.



El objetivo no es sustituir el criterio jurídico, sino:



\* localizar documentos relevantes;

\* detectar posibles plazos;

\* enriquecer `00\_CLIENTE.md`;

\* enriquecer `00\_EXPEDIENTE.md`;

\* generar un índice maestro de expedientes vivos;

\* generar una bandeja de posibles plazos;

\* separar los plazos confirmados por revisión humana;

\* producir un informe de control de plazos.



\## 2. Archivos principales



\### Archivos editables por humanos



Estos son los archivos que sí pueden editarse manualmente:



```text

D:\\DespachoOpsData\\Index\\hydrate\_whitelist.txt

D:\\DespachoOpsData\\Index\\hydrate\_blacklist.txt

D:\\DespachoOpsData\\Index\\hydrate\_expediente\_whitelist.txt

D:\\DespachoOpsData\\Index\\deadline\_candidates\_reviewed\_fixed.csv

D:\\DespachoOpsData\\Index\\confirmed\_deadlines\_working.csv

```



Especialmente importante:



```text

confirmed\_deadlines\_working.csv

```



Es el archivo humano de control de plazos confirmados. Ahí se rellenan manualmente:



```text

fecha\_notificacion

fecha\_vencimiento

actuacion

responsable

estado\_plazo

calendar\_event\_id

```



\### Archivos generados automáticamente



Estos archivos no deben editarse manualmente porque pueden regenerarse:



```text

D:\\DespachoOpsData\\Index\\live\_expedientes\_index.csv

D:\\DespachoOpsData\\Index\\deadline\_candidates.csv

D:\\DespachoOpsData\\Index\\confirmed\_deadlines.csv

D:\\DespachoOpsData\\Index\\deadline\_control\_report.xlsx

```



También son generados automáticamente los bloques Index dentro de:



```text

00\_CLIENTE.md

00\_EXPEDIENTE.md

```



Los bloques automáticos están delimitados por marcadores. No editar dentro de ellos.



\## 3. Flujo general



El flujo completo es:



```text

SQLite Index / OCR / enrichment

→ exportación de contexto por cliente

→ hidratación de 00\_CLIENTE.md

→ hidratación de 00\_EXPEDIENTE.md

→ live\_expedientes\_index.csv

→ deadline\_candidates.csv

→ revisión humana de candidatos

→ confirmed\_deadlines.csv

→ confirmed\_deadlines\_working.csv

→ deadline\_control\_report.xlsx

```



\## 4. Mantenimiento manual



El mantenimiento manual se lanza con:



```powershell

cd "D:\\Cebrian y Fraile Abogados\\DespachoOps\\despachoops-index"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\\scripts\\run\_live\_expedientes\_maintenance.ps1"

```



Resultado esperado:



```text

hydrate\_expediente\_md\_batch → OK

build\_live\_expedientes\_index → Resumen: {'OK': 21}

build\_deadline\_candidates → Candidatos plazo: 157

build\_deadline\_control\_report → Fin correcto

Fin mantenimiento expediente vivo exit=0

```



También puede lanzarse con:



```powershell

.\\scripts\\run\_live\_expedientes\_maintenance.bat

```



\## 5. Whitelist de clientes



Ruta:



```text

D:\\DespachoOpsData\\Index\\hydrate\_whitelist.txt

```



Controla qué clientes se hidratan con `00\_CLIENTE.md`.



\## 6. Blacklist de clientes



Ruta:



```text

D:\\DespachoOpsData\\Index\\hydrate\_blacklist.txt

```



Permite excluir clientes o carpetas que no deben hidratarse.



\## 7. Whitelist de expedientes



Ruta:



```text

D:\\DespachoOpsData\\Index\\hydrate\_expediente\_whitelist.txt

```



Formato:



```text

ruta\_json\_cliente|expediente|contains

```



Ejemplo:



```text

D:\\DespachoOpsData\\Index\\client\_context\_index\\harinas\_manzanares.json|AEAT escritos|Liquidación CCT 4T 2024

```



La whitelist de expedientes es la fuente de verdad para generar:



```text

00\_EXPEDIENTE.md

live\_expedientes\_index.csv

deadline\_candidates.csv

```



\## 8. `00\_CLIENTE.md`



Archivo situado en la carpeta raíz del cliente.



Ejemplo:



```text

\\\\Luiscp\\d\\Cebrian y Fraile Abogados\\Clientes\\Harinas Manzanares\\00\_CLIENTE.md

```



Contiene:



\* datos manuales del cliente;

\* resumen documental;

\* contexto generado por Index;

\* documentos relevantes;

\* posibles plazos detectados a nivel cliente.



No editar dentro del bloque automático.



\## 9. `00\_EXPEDIENTE.md`



Archivo situado en la carpeta concreta del expediente.



Ejemplo:



```text

\\\\Luiscp\\d\\Cebrian y Fraile Abogados\\Clientes\\Harinas Manzanares\\AEAT escritos\\Liquidación CCT 4T 2024\\00\_EXPEDIENTE.md

```



Contiene:



\* resumen del expediente;

\* documentos con posibles plazos;

\* documentos relevantes;

\* datos detectados por Index en bloque plegable `<details>`.



No editar dentro del bloque automático.



\## 10. Índice maestro de expedientes vivos



Archivo:



```text

D:\\DespachoOpsData\\Index\\live\_expedientes\_index.csv

```



Sirve para controlar todos los expedientes vivos generados.



Debe mostrar:



```text

status = OK

```



en todos los expedientes incluidos en whitelist.



Si aparece:



```text

ERROR

FALTA\_MD

REVISAR

```



hay que revisar la carpeta, el `00\_EXPEDIENTE.md` o los marcadores automáticos.



\## 11. Candidatos de plazo



Archivo generado:



```text

D:\\DespachoOpsData\\Index\\deadline\_candidates.csv

```



Contiene posibles plazos detectados por Index.



No es una agenda. No es una verdad jurídica. Es una bandeja de revisión.



Estados posibles en `estado\_revision`:



```text

pendiente

confirmado

descartado

histórico

dudoso

```



\### confirmado



Plazo real que debe controlarse.



\### descartado



Falso positivo.



\### histórico



Fue un plazo real, pero ya no es operativo porque está contestado, cumplido, vencido sin interés o superado por actuación posterior.



\### dudoso



Requiere abrir el documento y revisar manualmente.



\## 12. Candidatos revisados



Archivo humano saneado:



```text

D:\\DespachoOpsData\\Index\\deadline\_candidates\_reviewed\_fixed.csv

```



Este archivo contiene la revisión humana de candidatos.



No usar versiones corruptas con mojibake. Si aparece texto como:



```text

NotificaciÃ³n

dÃ­as

InspecciÃ³n

```



hay que reparar el CSV antes de usarlo.



Script reparador:



```powershell

.\\.venv\\Scripts\\python.exe .\\scripts\\repair\_mojibake\_csv.py --input "D:\\DespachoOpsData\\Index\\deadline\_candidates\_reviewed.csv" --output "D:\\DespachoOpsData\\Index\\deadline\_candidates\_reviewed\_fixed.csv"

```



\## 13. Plazos confirmados



Archivo generado:



```text

D:\\DespachoOpsData\\Index\\confirmed\_deadlines.csv

```



Se genera desde:



```text

deadline\_candidates\_reviewed\_fixed.csv

```



Incluye solo filas con:



```text

estado\_revision = confirmado

```



Ya contiene columnas operativas vacías:



```text

fecha\_notificacion

fecha\_vencimiento

actuacion

responsable

estado\_plazo

calendar\_event\_id

```



\## 14. Archivo humano de plazos confirmados



Archivo editable:



```text

D:\\DespachoOpsData\\Index\\confirmed\_deadlines\_working.csv

```



Este es el archivo que se rellena a mano.



Campos principales:



```text

fecha\_notificacion

fecha\_vencimiento

actuacion

responsable

estado\_plazo

```



Formato recomendado de fecha:



```text

AAAA-MM-DD

```



Ejemplo:



```text

2026-06-01

2026-06-16

```



Estados recomendados para `estado\_plazo`:



```text

pendiente

hecho

vencido

descartado

```



\## 15. Informe de control de plazos



Archivo generado:



```text

D:\\DespachoOpsData\\Index\\deadline\_control\_report.xlsx

```



No se edita manualmente.



Se genera desde:



```text

confirmed\_deadlines\_working.csv

```



Tiene pestañas:



```text

pendientes

sin\_fecha

vencidos

hechos

todos

```



La clasificación se hace así:



\* `hechos`: `estado\_plazo = hecho`;

\* `sin\_fecha`: no hay `fecha\_vencimiento`;

\* `vencidos`: fecha de vencimiento anterior a hoy y no está hecho;

\* `pendientes`: fecha de vencimiento futura o actual y no está hecho.



\## 16. Regla crítica



No editar manualmente:



```text

deadline\_control\_report.xlsx

```



Ese archivo es una salida generada.



Editar manualmente:



```text

confirmed\_deadlines\_working.csv

```



Después regenerar el informe.



\## 17. Scripts principales



```text

scripts\\export\_client\_context\_from\_index.py

scripts\\hydrate\_client\_md\_from\_index.py

scripts\\hydrate\_client\_md\_batch.py

scripts\\preview\_expediente\_md\_from\_index.py

scripts\\hydrate\_expediente\_md\_from\_index.py

scripts\\hydrate\_expediente\_md\_batch.py

scripts\\build\_live\_expedientes\_index.py

scripts\\build\_deadline\_candidates.py

scripts\\build\_confirmed\_deadlines.py

scripts\\build\_deadline\_control\_report.py

scripts\\csv\_to\_xlsx.py

scripts\\repair\_mojibake\_csv.py

scripts\\run\_live\_expedientes\_maintenance.ps1

scripts\\run\_live\_expedientes\_maintenance.bat

```



\## 18. Comandos útiles



\### Ejecutar mantenimiento completo



```powershell

powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\\scripts\\run\_live\_expedientes\_maintenance.ps1"

```



\### Regenerar índice maestro



```powershell

.\\.venv\\Scripts\\python.exe .\\scripts\\build\_live\_expedientes\_index.py --config .\\config.yaml --whitelist "D:\\DespachoOpsData\\Index\\hydrate\_expediente\_whitelist.txt" --output "D:\\DespachoOpsData\\Index\\live\_expedientes\_index.csv"

```



\### Regenerar candidatos de plazo



```powershell

.\\.venv\\Scripts\\python.exe .\\scripts\\build\_deadline\_candidates.py --config .\\config.yaml --whitelist "D:\\DespachoOpsData\\Index\\hydrate\_expediente\_whitelist.txt" --output "D:\\DespachoOpsData\\Index\\deadline\_candidates.csv"

```



\### Regenerar confirmados



```powershell

.\\.venv\\Scripts\\python.exe .\\scripts\\build\_confirmed\_deadlines.py --input "D:\\DespachoOpsData\\Index\\deadline\_candidates\_reviewed\_fixed.csv" --output "D:\\DespachoOpsData\\Index\\confirmed\_deadlines.csv"

```



\### Regenerar informe de control



```powershell

.\\.venv\\Scripts\\python.exe .\\scripts\\build\_deadline\_control\_report.py --input "D:\\DespachoOpsData\\Index\\confirmed\_deadlines\_working.csv" --output "D:\\DespachoOpsData\\Index\\deadline\_control\_report.xlsx"

```



\## 19. Estado actual de referencia



Estado estable a 2026-06-23:



```text

Expedientes vivos: 21

live\_expedientes\_index: 21 OK

deadline\_candidates: 157

plazos confirmados: 1

deadline\_control\_report:

\- pendientes: 0

\- sin\_fecha: 0

\- vencidos: 0

\- hechos: 1

```



\## 20. Próximos pasos posibles



No activar calendario automático todavía.



Antes:



1\. usar el sistema varios días;

2\. confirmar más plazos reales;

3\. revisar falsos positivos;

4\. mejorar reglas de candidatos si hace falta;

5\. crear `calendar\_sync\_confirmed\_deadlines.py` solo cuando haya suficientes confirmados y confianza en el flujo.



\## 21. Principio de seguridad



Index propone.



El abogado confirma.



Solo lo confirmado puede pasar a control de plazo o calendario.



