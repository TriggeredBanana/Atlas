---
layout: default
---
<div id="top"></div>
<div align="center">
  <img id="atlas-logo" src="assets/norkartFull.png" alt="Atlas" width="400" />
  <p><em>AI-assistert geospatialt arbeidsverktøy for kartanalyse og KU-relaterte arbeidsflyter</em></p>
</div>

---
## Oversikt

Atlas er en GeoMCP-chatbot utviklet for å assistere saksbehandlere i arbeid med norske konsekvensutredninger (KU). Assistenten kombinerer et interaktivt kart, dokumentbasert kontekst og romlige analyser i ett grensesnitt – og lar brukere stille faglige spørsmål, hente geodata og eksportere kartlag uten å forlate arbeidsflaten.

---
<div id="personlige-brukere"></div>
## Personlige Brukere

### Registrering

![Register flow](assets/registermodal.gif)

Nye brukere kan registrere seg gjennom logg inn-knappen.

### Innlogging 

![Login flow](assets/loginmodal.gif)


Eksisterende brukere logger inn gjennom samme knapp. 

---
<div id="chat"></div>
## Chat

### Send Melding

![Sende melding](assets/sendChat.gif) 

Skriv enkelt spørsmål eller forespørsler, og få svar fra assistenten.

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
<div id="kart"></div>
## Kart

### Kartvisninger 
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
<div id="verktoy"></div>
## Verktøy i aksjon

**1 — Velg og send verktøy**

![Tool sidebar](assets/SidebarTools.gif)

**2 — Resultat fra assistenten**

![Tool result](assets/ToolUsed.png)

---
<div id="eksport"></div>
## Eksport

![Export panel](assets/ExportLayers.gif)

Valgte lag kan eksporteres direkte fra nettleseren:

- **GeoJSON** — råformat for videre databehandling
- **JSON** — generisk format
- **PNG** — kartskisse som bilde
- **PDF** — kartskisse klar for rapport

---
<div id="modus"></div>
## Mørk og lys modus

![Dark/light mode toggle](assets/EditedLightmode.gif)

Atlas støtter mørk og lys modus og husker innstillingen i nettleseren.

---
<div id="video"></div>
## Demonstrasjonsvideo

<div align="center">
  <div class="video-wrapper">
    <iframe
      src="https://www.youtube.com/embed/pPJkSxmbnVA"
      title="Atlas demonstrasjonsvideo"
      frameborder="0"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowfullscreen>
    </iframe>
  </div>
</div>

---
<div id="prototype"></div>
## Fra prototype til Atlas

<p><em>Utviklingsprosessen og tidlige prototyper</em></p>

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
  <img src="assets/Tobiasproto1.png" alt="Prototype 2" width="80%">
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

<div id="sidebar-nav">
  <a href="#top">Tilbake til Topp</a>
  <a href="#personlige-brukere">Brukere</a>
  <a href="#chat">Chat</a>
  <a href="#kart">Kart</a>
  <a href="#verktoy">Verktøy</a>
  <a href="#eksport">Eksport</a>
  <a href="#modus">Modus</a>
  <a href="#video">Video</a>
  <a href="#prototype">Prototype</a>
</div>

<button id="hamburger-btn" aria-label="Åpne navigasjon">
  <span class="hbar"></span>
  <span class="hbar"></span>
  <span class="hbar"></span>
</button>

<div id="nav-overlay"></div>

<div id="nav-drawer">
  <a href="#top">Tilbake til topp</a>
  <a href="#personlige-brukere">Brukere</a>
  <a href="#chat">Chat</a>
  <a href="#kart">Kart</a>
  <a href="#verktoy">Verktøy</a>
  <a href="#eksport">Eksport</a>
  <a href="#modus">Modus</a>
  <a href="#video">Video</a>
  <a href="#prototype">Prototype</a>
</div>

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

.video-wrapper{
  position: relative;
  width: 80%;
  margin: 0 auto;
  aspect-ratio: 16 / 9;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.video-wrapper iframe{
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
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

html{
  scroll-behavior: smooth;
}

#sidebar-nav{
  position: fixed;
  left: 1rem;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  border-radius: 14px;
  background: rgba(255,255,255,0.75);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(0,0,0,0.08);
  z-index: 999;
}

#sidebar-nav a,
#nav-drawer a{
  text-decoration: none;
  color: inherit;
  font-size: 0.9rem;
  opacity: 0.8;
  transition: opacity 0.2s ease;
}

#sidebar-nav a:hover{
  opacity: 1;
}

body.dark #sidebar-nav{
  background: rgba(20,20,20,0.55);
  border: 1px solid rgba(255,255,255,0.12);
}

#hamburger-btn {
  display: none;
  position: fixed;
  top: 1rem;
  left: 1rem;
  z-index: 1001;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  border: 1px solid rgba(0,0,0,0.08);
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  cursor: pointer;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 11px 10px;
}

body.dark #hamburger-btn {
  background: rgba(20,20,20,0.55);
  border: 1px solid rgba(255,255,255,0.12);
}

.hbar {
  width: 20px;
  height: 2px;
  background: #111;
  border-radius: 2px;
  transition: all 0.25s;
  display: block;
}

body.dark .hbar { background: #fff; }

#hamburger-btn.open .hbar:nth-child(1) { transform: translateY(7px) rotate(45deg); }
#hamburger-btn.open .hbar:nth-child(2) { opacity: 0; }
#hamburger-btn.open .hbar:nth-child(3) { transform: translateY(-7px) rotate(-45deg); }

#nav-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.35);
  z-index: 999;
}

#nav-overlay.open { display: block; }

#nav-drawer {
  display: flex;
  visibility: hidden;
  pointer-events: none;
  position: fixed;
  top: 0; left: 0;
  height: 100%;
  width: 200px;
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 0 14px 14px 0;
  z-index: 1000;
  padding: 72px 0.75rem 1.5rem;
  flex-direction: column;
  gap: 0.5rem;
  transform: translateX(-100%);
  transition: transform 0.25s ease;
}

body.dark #nav-drawer {
  background: rgba(20,20,20,0.55);
  border: 1px solid rgba(255,255,255,0.12);
}

#nav-drawer.open { 
  transform: translateX(0); 
  visibility: visible;
  pointer-events: auto;
  }

#nav-drawer a:hover { opacity: 1; }

@media (max-width: 768px) {
  #sidebar-nav { display: none; }
  #hamburger-btn { display: flex; }
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

const hbtn = document.getElementById('hamburger-btn');
const drawer = document.getElementById('nav-drawer');
const navOverlay = document.getElementById('nav-overlay');

function closeDrawer() {
  drawer.classList.remove('open');
  navOverlay.classList.remove('open');
  hbtn.classList.remove('open');
}

hbtn.addEventListener('click', () => {
  const isOpen = drawer.classList.toggle('open');
  navOverlay.classList.toggle('open', isOpen);
  hbtn.classList.toggle('open', isOpen);
});

navOverlay.addEventListener('click', closeDrawer);
drawer.querySelectorAll('a').forEach(a => a.addEventListener('click', closeDrawer));
</script>
