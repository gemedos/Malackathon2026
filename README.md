### Malackathon2026
# Carpeta reports
Esta carpeta contiene el report con al menos un test fallido, además de la entrada que ocasiona dicho report, en la carpeta artifact

# Script make_report.py
Este script se encarga de generar un report en formato html (report.html) a partir de un fichero JSON (results.json). Para que este script funcione, la carpeta artifacts (generada por el programa encargado de entrar a la casa de apuestas), debe estar en el mismo nivel de directorio que este script. En otro caso, la línea 7 "SRC = sys.argv[1] if len(sys.argv) > 1 else "artifacts/es/results.json"", habría que modificarla por "SRC = sys.argv[1] if len(sys.argv) > 1 else "<nombreCarpeta>/artifacts/es/results.json"". Otro modo de usar este script es pasándo la ruta donde se encuentra el JSON (argumento 1) y dónde queremos que se guarde el report (argumento 2). 
