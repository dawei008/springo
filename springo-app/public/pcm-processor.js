class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.outBuffer = new Float32Array(4096);
    this.outOffset = 0;
    this.srcFraction = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) return true;
    const data = input[0];

    let i = this.srcFraction;
    while (i < data.length) {
      const idx = Math.floor(i);
      const frac = i - idx;
      const s0 = data[idx];
      const s1 = idx + 1 < data.length ? data[idx + 1] : s0;
      this.outBuffer[this.outOffset++] = s0 + (s1 - s0) * frac;
      i += this.ratio;

      if (this.outOffset >= 4096) {
        this.port.postMessage(this.outBuffer);
        this.outBuffer = new Float32Array(4096);
        this.outOffset = 0;
      }
    }
    this.srcFraction = i - data.length;
    return true;
  }
}
registerProcessor('pcm-capture', PcmCaptureProcessor);
