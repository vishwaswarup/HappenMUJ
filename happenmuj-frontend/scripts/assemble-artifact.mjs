// Turns dist-artifact/app.js + app.css into one HTML fragment for the Artifact tool.
// The host supplies the document skeleton, so this emits only title, fonts, style, root, scripts.
import { readFileSync, writeFileSync } from 'node:fs';

const js = readFileSync('dist-artifact/app.js', 'utf8').replace(/<\/script/gi, '<\\/script');
const css = readFileSync('dist-artifact/app.css', 'utf8').replace(/<\/style/gi, '<\\/style');
const fonts = 'https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@600;700;800&family=Hanken+Grotesk:wght@400;500;600;700&display=swap';

const html = `<title>HappenMUJ</title>
<link rel="stylesheet" href="${fonts}">
<style>${css}</style>
<div id="root"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js"></script>
<script>${js}</script>
`;
writeFileSync('dist-artifact/artifact.html', html);
console.log(`artifact.html ${(html.length / 1024).toFixed(0)} KB`);
