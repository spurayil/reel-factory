// Deterministic renderer: timeline.json -> headless Chrome frames -> FFmpeg H.264 1080x1920.
// node render.js timeline.json out.mp4 [--stills 1.2,5.0,9.8]
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const puppeteer = require("puppeteer-core");

const CHROME_PATHS = [
  process.env.CHROME_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  path.join(process.env.LOCALAPPDATA || "", "Google\\Chrome\\Application\\chrome.exe"),
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].filter(Boolean);

async function main() {
  const [tlPath, outPath, ...rest] = process.argv.slice(2);
  const stillsArg = rest.indexOf("--stills") >= 0 ? rest[rest.indexOf("--stills") + 1] : null;
  const tl = JSON.parse(fs.readFileSync(tlPath, "utf-8"));
  const chrome = CHROME_PATHS.find((p) => fs.existsSync(p));
  if (!chrome) throw new Error("Chrome not found");

  const browser = await puppeteer.launch({
    executablePath: chrome,
    headless: true,
    args: ["--allow-file-access-from-files", "--disable-gpu", "--hide-scrollbars", "--force-color-profile=srgb"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: tl.width, height: tl.height, deviceScaleFactor: 1 });
  const url = "file:///" + path.join(__dirname, "template", "index.html").replace(/\\/g, "/");
  await page.goto(url, { waitUntil: "load" });
  await page.evaluate(async (t) => { await window.setup(t); }, tl);

  if (stillsArg) {
    const times = stillsArg.split(",").map(Number);
    const base = outPath.replace(/\.jpg$/, "");
    for (let i = 0; i < times.length; i++) {
      await page.evaluate((t) => window.renderAt(t), times[i]);
      await page.screenshot({ path: `${base}_${String(i + 1).padStart(2, "0")}.jpg`, type: "jpeg", quality: 92 });
    }
    await browser.close();
    console.log(`      ${times.length} stills written`);
    return;
  }

  const total = Math.ceil(tl.duration * tl.fps);
  const ff = spawn("ffmpeg", [
    "-y", "-v", "error", "-f", "image2pipe", "-framerate", String(tl.fps), "-c:v", "mjpeg", "-i", "-",
    "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p", "-color_range", "tv",
    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
    "-r", String(tl.fps), "-movflags", "+faststart", outPath,
  ], { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res, rej) => ff.on("close", (c) => (c === 0 ? res() : rej(new Error("ffmpeg exit " + c)))));

  const t0 = Date.now();
  for (let f = 0; f < total; f++) {
    await page.evaluate((t) => window.renderAt(t), f / tl.fps);
    const buf = await page.screenshot({ type: "jpeg", quality: 92, optimizeForSpeed: true });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
    if (f % 150 === 0) process.stdout.write(`      frame ${f}/${total}\n`);
  }
  ff.stdin.end();
  await done;
  await browser.close();
  console.log(`      ${total} frames in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}

main().catch((e) => { console.error(e); process.exit(1); });
