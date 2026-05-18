---
layout: null
---

<div align="center">
  <img id="atlas-logo" src="assets/norkartFull.png" alt="Atlas" width="400" />
  <p><em>AI-assistert geospatialt arbeidsverktøy for kartanalyse og KU-relaterte arbeidsflyter</em></p>
</div>

---

## Oversikt

Atlas er en GeoMCP-chatbot utviklet for å assistere saksbehandlere i arbeid med norske konsekvensutredninger (KU). Assistenten kombinerer et interaktivt kart, dokumentbasert kontekst og romlige analyser i ett grensesnitt – og lar brukere stille faglige spørsmål, hente geodata og eksportere kartlag uten å forlate arbeidsflaten.

---

## Personlige Brukere

### Registrering

![Register flow](assets/registermodal.gif)

Nye brukere kan registrere seg gjennom logg inn knappen.

### Innlogging 

![Login flow](assets/loginmodal.gif)


Eksisterende brukere logger inn gjennom samme knapp. 

---

## Chat

### Send Melding

![Sende melding](assets/sendChat.gif) 

Enkelt skriv spørsmål eller forespørsler, deretter få svar fra assistenten. 

---

### Samtalehistorikk
![Samtalehistorikk](assets/ChatHistory.gif)

Alle tidligere samtaler vises i sidepanelet. Klikk på en samtale for å åpne den igjen og fortsette der du slapp.

---

### Slette en samtale

![Slette samtale](assets/deleteChats.gif)

Samtaler kan slettes enkeltvis fra historikkpanelet.

---

### Tokenforbruk

![Token usage](assets/tokenusage.gif)

Brukere kan se tokenforbruk per melding direkte i chatten.

---

##  Kart

### Kart Visninger 
![Map overview](assets/Basemaps.gif)

Kartarbeidsområdet er sentrert på Norge med bakgrunnskart fra Kartverket og flyfoto fra Esri.
Brukere kan bytte mellom bakgrunnskart i sanntid.

---

### Tegning i kart

![Drawing tools](assets/MapDraw.gif)

Leaflet gir tilgang til tegning av markører, polygoner, rektangler, linjer og sirkler,
samt redigering og fjerning av eksisterende lag. Posisjonering bruker nettleserens Geolocation API.

### Laghåndtering

![Layer management](assets/MapLayersSidebar.gif)

Hvert kartlag kan skjules, vises på nytt eller slettes fra sidepanelet.
AI-genererte lag og brukerens egne lag behandles likt.

---

## Verktøy i aksjon

**1 — Velg og send verktøy**

![Tool sidebar](assets/SidebarTools.gif)

**2 — Resultat fra assistenten**

![Tool result](assets/ToolUsed.png)

---

## Eksport

![Export panel](assets/ExportLayers.gif)

Valgte lag kan eksporteres direkte fra nettleseren:

- **GeoJSON** — råformat for videre databehandling
- **JSON** — generisk format
- **PNG** — kartskisse som bilde
- **PDF** — kartskisse klar for rapport

---

## Mørk og lys modus

![Dark/light mode toggle](assets/EditedLightmode.gif)

Atlas støtter mørk og lys modus med persistent lagring i nettleseren.

---
## Fra prototype til Atlas

<p><em>Utviklingsprossessen og tidlige prototyper</em></p>

### Prototype 1 — Første konsept

<div align="center">
  <img src="assets/FirstPrototype.png" alt="Prototype 1" width="80%">
</div>

<p align="center">
  <em>Første fungerende prototype med bufferhåndtering og kart-output.</em>
</p>

---

### Prototype 2 — UI-konsept

<div align="center">
  <img src="assets/TobiasProto1.png" alt="Prototype 2" width="80%">
</div>

<p align="center">
  <em>Første frontend-konsept med fokus på layout og brukeropplevelse.</em>
</p>

---

### Prototype 3 — UI iterasjon

<div align="center">
  <img src="assets/TobiasProto2.png" alt="Prototype 3" width="80%">
</div>

<p align="center">
  <em>Videreutvikling av panelsystem, navigasjon og visuell struktur.</em>
</p>

---

### Prototype 4 — Designforfining

<div align="center">
  <img src="assets/SigurdPrototype.png" alt="Prototype 4" width="80%">
</div>

<p align="center">
  <em>Videre modning av interaksjonsdesign og arbeidsflyt.</em>
</p>

---

### Prototype 5 — Funksjonell arbeidsflyt

<p><em>En interaktiv prototype som demonstrerer kartarbeid og analyse i praksis.</em></p>

<div class="prototype-gallery">
  <a href="assets/Danielproto1.png" target="_blank"><img src="assets/Danielproto1.png"></a>
  <a href="assets/Danielproto2.png" target="_blank"><img src="assets/Danielproto2.png"></a>
  <a href="assets/Danielproto3.png" target="_blank"><img src="assets/Danielproto3.png"></a>
  <a href="assets/Danielproto4.png" target="_blank"><img src="assets/Danielproto4.png"></a>
  <a href="assets/Danielproto5.png" target="_blank"><img src="assets/Danielproto5.png"></a>
  <a href="assets/Danielproto6.png" target="_blank"><img src="assets/Danielproto6.png"></a>
</div>

---

<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">

<style>
  body{
  background: #ffffff;
  color: #111;
}

  body.dark{
  background: #0d1117;
  color: #c9d1d9;
}

#floating-controls{
  position: fixed;
  top: 1.5rem;
  right: 1.5rem;
  z-index: 999;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.floating-btn{
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  border: 1px solid rgba(0,0,0,0.08);
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  cursor: pointer;
  transition: all 0.2s ease;
  color: #111;
}

.floating-btn:hover{
  transform: translateY(-2px);
  background: rgba(255,255,255,1);
}

body.dark .floating-btn{
  background: rgba(20, 20, 20, 0.55);
  border: 1px solid rgba(255,255,255,0.12);
  color: #fff;
}

body.dark .floating-btn:hover{
  background: rgba(30, 30, 30, 0.75);
}

.floating-btn i{
  font-size: 18px;
}

.prototype-gallery{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.prototype-gallery img{
  width: 100%;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  transition: transform 0.2s ease;
  cursor: pointer;
}

.prototype-gallery img:hover{
  transform: scale(1.02);
}

.prototype-gallery a{
  display: block;
}
</style>

<div id="floating-controls">
  <a class="floating-btn" id="github-link" href="https://github.com/KartAI/Atlas" target="_blank" aria-label="GitHub">
   <i class="fa-brands fa-github"></i>
  </a>
  <button class="floating-btn" id="theme-toggle">
   <i id="theme-icon" class="fa-solid fa-moon"></i>
  </button>
</div>

<script>
 const btn = document.getElementById('theme-toggle');
const icon = document.getElementById('theme-icon');
const logo = document.getElementById('atlas-logo');

const apply = dark => {
  document.body.classList.toggle('dark', dark);

  if (icon) {
    icon.className = dark ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
  }

  if (logo) {
    logo.src = dark
      ? 'assets/norkartFull_white.png'
      : 'assets/norkartFull.png';
  }
};

const saved = localStorage.getItem('theme');
const systemDark = window.matchMedia &&
  window.matchMedia('(prefers-color-scheme: dark)').matches;

apply(saved ? saved === 'dark' : systemDark);

btn.addEventListener('click', () => {
  const dark = !document.body.classList.contains('dark');
  localStorage.setItem('theme', dark ? 'dark' : 'light');
  apply(dark);
});
</script>
