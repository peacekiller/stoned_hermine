# "Stoned Hermine"

Eine kleine Python-Anwendung welche Änderungen an `Assets` (=Einheiten, Geräte, Sonderfunktionen, etc.) in der Stein.App bemerkt und diese dann in 
einen Hermine-Channel pusht.


Danke an dieser Stelle 

* an Anselm Eberhardt für den Stashcat-Client, mit dem die Nachrichten nach Hermine gesendet werden:
https://gitlab.com/aeberhardt/stashcat-api-client

* 'oscarminus' für den stein.app-Client: https://github.com/oscarminus/steinapi/blob/main/steinapi.py


## Setup
### Konfiguration
Es existiert eine Beispielkonfiguration mit dem Namen `config.example.ini`. Diese am besten nach config.ini 
umbenennen und die Platzhalter in den Sektionen `[stein.app]` und `[hermine]` ersetzen.

### Notwendige Python-Module installieren
Die benötigten Module stehen in der Datei `requirements.txt` und können mit folgendem Befehl installiert werden:
``pip3 install -r requirements.txt``

## Starten
`./SteinConnector.py`