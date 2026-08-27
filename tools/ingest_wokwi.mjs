#!/usr/bin/env node
/**
 * Extract pictorial component art from @wokwi/elements into hardware/parts/wokwi/.
 *
 * Run rarely, commit the output. CI never runs this and never needs the network.
 *
 * WHY A HEADLESS BROWSER RATHER THAN PARSING THE SOURCE
 *
 * Wokwi elements are lit web components: the SVG lives inside a tagged template
 * literal with ${...} interpolations (a resistor computes its colour bands from its
 * `value` property at render time). Statically parsing that template means
 * reimplementing the interpolation and getting a different picture from the one
 * users actually see. Rendering the real component and serialising what it produced
 * is both simpler and correct by construction.
 *
 * WHAT WE TAKE, AND WHY IT IS ONLY THE DISCRETE PARTS
 *
 * Wokwi's ESP32 element is a DevKit **v1**: 30 pins, Arduino-style D13/D25 naming.
 * This project uses a DevKitC-32E: 38 pins, and the firmware speaks GPIO numbers.
 * Relabelling someone else's board art into a board we do not own is how a diagram
 * ends up lying, so the board is drawn by us (tools/partlib.py) and only the
 * discrete parts come from here.
 *
 * The real prize is the CONTRACT, not the pictures. Every element exposes
 *   pinInfo = [{ name, x, y, signals, description }]
 * and adopting that shape for our own parts makes the two interchangeable: the
 * router cannot tell which is which, and anything Wokwi adds later drops straight in.
 *
 *   npm i playwright && node tools/ingest_wokwi.mjs
 */

import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.join(REPO, 'hardware', 'parts', 'wokwi');

// Pinned. An unpinned ingestion means the committed art can change under us with
// no diff in this repository to explain why.
const PKG = '@wokwi/elements';
const VERSION = '1.9.2';

// Only what this project actually uses. Taking all 50 would be committing art for
// servos and LCD panels a table saw has no use for.
const WANT = [
  { el: 'wokwi-resistor',                use: 'R1 divider, R2 GPIO26 pulldown, R3 opto series' },
  { el: 'wokwi-pushbutton',              use: 'acknowledge button on GPIO27' },
  { el: 'wokwi-led',                     use: 'status LED, where an external one is fitted' },
  { el: 'wokwi-ntc-temperature-sensor',  use: 'stands in for the DROK frame probe RT1' },
  { el: 'wokwi-ks2e-m-dc5',              use: 'relay — Path B KA2, not purchased' },
  { el: 'wokwi-slide-switch',            use: 'generic two-position switch' },
];

async function main() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'wokwi-'));
  const tgz = path.join(tmp, 'el.tgz');
  const url = `https://registry.npmjs.org/${PKG}/-/elements-${VERSION}.tgz`;
  console.log(`  fetching ${PKG}@${VERSION}`);
  execSync(`curl -sSL --max-time 120 -o "${tgz}" "${url}"`);
  execSync(`tar -xzf "${tgz}" -C "${tmp}"`);

  const bundlePath = path.join(tmp, 'package', 'dist', 'wokwi-elements.bundle.js');
  const licence = fs.readFileSync(path.join(tmp, 'package', 'LICENSE'), 'utf8');
  const bundle = fs.readFileSync(bundlePath, 'utf8');
  console.log(`  bundle ${(bundle.length / 1024).toFixed(0)} KB`);

  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium',
  });
  const page = await browser.newPage();
  await page.setContent('<!doctype html><body></body>');
  await page.addScriptTag({ content: bundle });

  const wanted = WANT.map(w => w.el);
  const got = await page.evaluate(async (names) => {
    const out = [];
    for (const name of names) {
      if (!customElements.get(name)) { out.push({ name, ok: false, why: 'not registered' }); continue; }
      const el = document.createElement(name);
      document.body.appendChild(el);
      // Give lit a frame to render into the shadow root.
      await new Promise(r => requestAnimationFrame(() => setTimeout(r, 30)));
      const svg = el.shadowRoot && el.shadowRoot.querySelector('svg');
      if (!svg) { out.push({ name, ok: false, why: 'no svg in shadow root' }); continue; }
      out.push({
        name, ok: true,
        svg: svg.outerHTML,
        viewBox: svg.getAttribute('viewBox'),
        width: svg.getAttribute('width'),
        height: svg.getAttribute('height'),
        pins: (el.pinInfo || []).map(p => ({
          name: p.name, x: p.x, y: p.y,
          signals: p.signals || [],
          description: p.description || null,
        })),
      });
    }
    return out;
  }, wanted);

  await browser.close();

  fs.mkdirSync(OUT, { recursive: true });
  const index = { source: {}, parts: {} };
  let failed = 0;

  for (const w of WANT) {
    const r = got.find(g => g.name === w.el);
    if (!r || !r.ok) { console.error(`  FAILED ${w.el}: ${r ? r.why : 'missing'}`); failed++; continue; }
    // lit leaves comment markers in the serialised DOM; they carry no meaning here.
    const svg = r.svg.replace(/<!--\??lit\$[^>]*-->/g, '').replace(/<!---->/g, '');
    fs.writeFileSync(path.join(OUT, `${r.name}.svg`), svg + '\n');
    index.parts[r.name] = {
      use: w.use,
      viewBox: r.viewBox, width: r.width, height: r.height,
      pins: r.pins,
      svg: `${r.name}.svg`,
    };
    console.log(`  ${r.name.padEnd(30)} ${String(r.pins.length).padStart(2)} pins  ` +
                `${String(svg.length).padStart(5)} B  [${r.pins.map(p => p.name).join(' ')}]`);
  }

  index.source = {
    package: PKG, version: VERSION, url,
    repository: 'https://github.com/wokwi/wokwi-elements',
    licence: 'MIT',
    copyright: (licence.match(/Copyright \(c\)[^\n]*/) || ['Copyright (c) Uri Shaked'])[0].trim(),
    note: 'Extracted by rendering the real components headlessly — see tools/ingest_wokwi.mjs. ' +
          'The ESP32 board is deliberately NOT taken from here: Wokwi ships a 30-pin DevKit v1 ' +
          'and this project uses a 38-pin DevKitC-32E.',
  };
  fs.writeFileSync(path.join(OUT, 'index.json'), JSON.stringify(index, null, 1) + '\n');
  fs.writeFileSync(path.join(OUT, 'LICENSE.wokwi'), licence);

  console.log(`\nwrote ${path.relative(REPO, OUT)}/  (${Object.keys(index.parts).length} parts)`);
  if (failed) { console.error(`${failed} element(s) failed`); process.exit(1); }
}

main().catch(e => { console.error(e); process.exit(1); });
