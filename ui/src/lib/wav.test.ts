import { describe, expect, it } from "vitest";
import { concatPcm, downmixToMono, encodeWavPcm16 } from "./wav";

describe("encodeWavPcm16", () => {
  it("writes a valid RIFF/WAVE header", () => {
    const pcm = new Float32Array([0, 0.5, -0.5, 1, -1]);
    const buf = encodeWavPcm16(pcm, 48000);
    const b = new Uint8Array(buf);
    expect(String.fromCharCode(...b.slice(0, 4))).toBe("RIFF");
    expect(String.fromCharCode(...b.slice(8, 12))).toBe("WAVE");
    const view = new DataView(buf);
    expect(view.getUint32(24, true)).toBe(48000); // sample rate
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint16(34, true)).toBe(16); // bits
    expect(view.getUint32(40, true)).toBe(pcm.length * 2); // data size
    expect(buf.byteLength).toBe(44 + pcm.length * 2);
  });

  it("clamps samples outside -1..1", () => {
    const buf = encodeWavPcm16(new Float32Array([2, -2]), 8000);
    const view = new DataView(buf);
    expect(view.getInt16(44, true)).toBe(0x7fff);
    expect(view.getInt16(46, true)).toBe(-0x8000);
  });
});

describe("pcm helpers", () => {
  it("downmixes channels to mono", () => {
    const mono = downmixToMono([new Float32Array([1, 1]), new Float32Array([0, 2])]);
    expect(Array.from(mono)).toEqual([0.5, 1.5]);
  });

  it("concatenates chunks", () => {
    const out = concatPcm([new Float32Array([1, 2]), new Float32Array([3])], 3);
    expect(Array.from(out)).toEqual([1, 2, 3]);
  });
});
