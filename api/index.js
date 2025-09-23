import express from "express";
import { spawn } from "child_process";
import path, { dirname } from "path";
import fs from "fs";
import multer from "multer";

const app = express();
app.use(express.json());
const upload = multer({ dest: 'uploads/' })


app.get("/validate", async (req, res) => {
  fs.rename(path.resolve("./uploads/9ce51225f4d3f238bcdad4938c1eaff1"), path.resolve("./uploads/9ce51225f4d3f238bcdad4938c1eaff1.mq5"), () => {

  })
  res.json({ success: true });
});

app.post('/get_account_data', (req, res) => {
  const { login, password, server } = req.body;

  if (!login || !password || !server)
    return res.status(400).json({ error: 'Missing fields' });

  const scriptPath = path.resolve("../scripts/account/index.py");
  const process = spawn('python', [scriptPath, login, password, server]);

  let data = '';
  process.stdout.on('data', chunk => data += chunk.toString());
  process.stderr.on('data', err => console.error('stderr:', err.toString()));
  process.on('close', code => {
    if (code === 0) res.json(JSON.parse(data));
    else res.status(500).json({ error: 'Failed to connect' });
  });
});


app.post("/validate", upload.single("code_file"), async (req, res) => {
  console.log({ file: req.file, body: req.body })
  try {

    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    const { file_extension } = req.body
    const { filename, destination } = req.file
    const filePath = path.resolve(`./${destination}${filename}.${file_extension}`)
    if (!filename.includes(".mq")) {
      fs.renameSync(path.resolve(`./${destination}${filename}`), path.resolve(`./${destination}${filename}.${file_extension}`))
    }
    // console.log({filePath, filename})

    const exFilePath = path.resolve(`./${destination}${filename}.${file_extension.replace("mq", "ex")}`)
    const rawFilePath = path.resolve(`./${destination}${filename}`)

    const scriptPath = path.resolve("../scripts/validate/index.py");
    const python = spawn("python", [scriptPath, filePath, filename, exFilePath, rawFilePath]);

    let output = "";
    let errorOutput = "";

    python.stdout.on("data", (data) => {
      output += data.toString();
    });

    python.stderr.on("data", (data) => {
      errorOutput += data.toString();
    });

    python.on("close", (code) => {
        console.log(JSON.parse(output))

      try {
        if (errorOutput) {
          return res.status(500).json({ error: errorOutput });
        }
        const result = JSON.parse(output);
        return res.json(result);
      } catch (err) {
        return res.status(500).json({ error: "Failed to parse Python output", details: output });
      }
    });

  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, message: "Server error" });
  }
});





const PORT = process.env.PORT || 4756;
app.listen(PORT, () => {
  console.log(`EA Compiler API running on port ${PORT} 🚀`);
});
