"""Alyans Dental intro – ses tasarımı (48 kHz stereo, tamamen sentez, telifsiz).

Kullanım: python sfx.py out.wav

Yapı (30 fps kare zaman çizelgesiyle eşleşir):
  0.00 s   karanlık gerilim dronu + ters reverb yükselişi
  0.83 s   "ta"   – yumuşak ön vuruş (işaret yaklaşırken)
  1.23 s   "DUM"  – derin, rezonanslı ana vuruş + açılan akor (işaret iner)
  2.37 s   "zım"  – metalik parlama (ışık süpürmesi)
  2.95 s   kalp atışı – gerilim
  3.57 s   vakum emişi – yükselen gerilim
  4.43 s   KESME: ekran direkt kararır – trailer "braam" vuruşu, uzun kuyruk
  6.20 s   son
"""
import sys
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
FPS = 30
END_FRAME = 186
CUT_FRAME = 134          # first black frame
DUR = END_FRAME / FPS
N = int(DUR * SR)
rng = np.random.default_rng(11)


def fr(f):
    """frame number -> seconds (frame 1 == t 0)"""
    return (f - 1) / FPS


def tax(n):
    return np.arange(n) / SR


def place(bus, x, t0, gain=1.0, pan=0.0):
    i0 = int(round(t0 * SR))
    if x.ndim == 1:
        if np.isscalar(pan):
            pan = np.full(len(x), pan)
        th = (np.asarray(pan) + 1) * np.pi / 4
        x = np.stack([x * np.cos(th), x * np.sin(th)], 1)
    i1 = min(len(bus), i0 + len(x))
    if i1 > i0 >= 0:
        bus[i0:i1] += gain * x[:i1 - i0]


def svf_bp(noise, fc_curve, q=2.0):
    n = len(noise)
    out = np.zeros(n)
    low = band = 0.0
    damp = 1.0 / q
    f = 2 * np.sin(np.pi * np.minimum(fc_curve, SR / 6) / SR)
    for i in range(n):
        high = noise[i] - low - damp * band
        band += f[i] * high
        low += f[i] * band
        out[i] = band
    return out


def lp(x, fc, order=2):
    b, a = signal.butter(order, fc / (SR / 2), 'low')
    return signal.lfilter(b, a, x, axis=0)


def hp(x, fc, order=2):
    b, a = signal.butter(order, fc / (SR / 2), 'high')
    return signal.lfilter(b, a, x, axis=0)


def tv_lowpass(x, fc_curve):
    """time-varying one-pole x2 low-pass"""
    y1 = y2 = 0.0
    out = np.zeros(len(x))
    a = 1 - np.exp(-2 * np.pi * np.minimum(fc_curve, SR / 3) / SR)
    for i in range(len(x)):
        y1 += a[i] * (x[i] - y1)
        y2 += a[i] * (y1 - y2)
        out[i] = y2
    return out


def osc_sine(freq_curve):
    return np.sin(2 * np.pi * np.cumsum(freq_curve) / SR)


def osc_saw(freq_curve, phase=0.0):
    ph = (np.cumsum(freq_curve) / SR + phase) % 1.0
    return 2 * ph - 1


def reverb_ir(seconds, decay, predelay=0.015, bright=6500):
    n = int(seconds * SR)
    t = tax(n)
    ir = rng.standard_normal((n, 2)) * np.exp(-t / decay)[:, None]
    ir = lp(ir, bright)
    ir = np.concatenate([np.zeros((int(predelay * SR), 2)), ir])
    return ir / np.sqrt(np.sum(ir ** 2) / 2)


dry = np.zeros((N, 2))
hall = np.zeros((N, 2))      # medium reverb send
cave = np.zeros((N, 2))      # long dark reverb send (big hits)

T_TA, T_DUM = fr(26), fr(38)
T_ZIM = fr(72)
T_CUT = fr(CUT_FRAME)

# ---------------------------------------------------------------- 1. tension drone + reverse swell into the logo hit
n = int((T_DUM + 0.05) * SR)
t = tax(n)
drone = (np.sin(2 * np.pi * 41.2 * t) + 0.45 * np.sin(2 * np.pi * 61.7 * t + 1)
         + 0.2 * osc_saw(np.full(n, 82.4)) * 0.5)
drone = lp(drone, 400) * np.minimum(t / 0.6, 1) * 0.55
swell = svf_bp(rng.standard_normal(n), 220 * (4800 / 220) ** (t / t[-1]), q=1.3)
swell *= (t / t[-1]) ** 3.2
place(dry, drone * 0.22, 0.0)
place(dry, swell * 0.20, 0.0, pan=np.linspace(-0.35, 0.0, n))
place(hall, swell * 0.25, 0.0)
# suck-out: tiny gap right before "ta"
# (handled implicitly: swell peaks at DUM, ta sits inside it)

# ---------------------------------------------------------------- 2. whoosh – mark flies in
w0, w1 = fr(8), fr(36)
n = int((w1 - w0 + 0.2) * SR)
u = np.linspace(0, 1, n)
fc = 300 + 2200 * np.sin(np.pi * np.clip(u * 1.05, 0, 1)) ** 2
wh = svf_bp(rng.standard_normal(n), fc, q=1.8) * np.exp(-((u - 0.62) / 0.26) ** 2)
place(dry, wh * 0.42, w0, pan=np.linspace(-0.85, 0.05, n))
place(hall, wh * 0.25, w0)


# ---------------------------------------------------------------- 3. "ta–DUM" sonic logo (original)
def tuned_hit(f0, length, decays, amps, drop=0.05, click=0.2, thump=0.7):
    n_ = int(length * SR)
    t_ = tax(n_)
    glide = 1 + drop * np.exp(-t_ / 0.06)
    body = np.zeros(n_)
    for k, (dk, ak) in enumerate(zip(decays, amps)):
        body += ak * osc_sine(f0 * (k + 1) * glide) * np.exp(-t_ / dk)
    body *= np.minimum(t_ / 0.003, 1)
    th = lp(rng.standard_normal(n_), 180, 4) * np.exp(-t_ / 0.05) * thump
    ck = hp(rng.standard_normal(n_), 1800, 2) * np.exp(-t_ / 0.006) * click
    return body + th + ck


ta = tuned_hit(58.3, 1.2, [0.22, 0.14, 0.09], [1.0, 0.55, 0.3], click=0.25, thump=0.6)
dum = tuned_hit(49.0, 3.2, [1.1, 0.7, 0.45, 0.3], [1.0, 0.65, 0.4, 0.2], drop=0.07, click=0.3, thump=1.0)
place(dry, ta * 0.50, T_TA)
place(hall, ta * 0.30, T_TA)
place(dry, dum * 0.95, T_DUM)
place(cave, dum * 0.35, T_DUM)

# bloom: open chord that swells after DUM (G1 D2 G2 D3 B3), wide stereo, filter opens then closes
n = int(2.6 * SR)
t = tax(n)
chord = np.zeros((n, 2))
for i_, (f, a) in enumerate([(49.0, 1.0), (73.4, 0.8), (98.0, 0.7), (146.8, 0.5), (246.9, 0.28)]):
    for ch, det in enumerate((-0.006, 0.006)):
        chord[:, ch] += a * osc_saw(np.full(n, f * (1 + det * (1 + i_ * 0.3))), phase=rng.random())
cut_curve = 150 + 1900 * np.sin(np.pi * np.clip(t / 1.6, 0, 1)) ** 1.5 * np.exp(-t / 1.4)
for ch in range(2):
    chord[:, ch] = tv_lowpass(chord[:, ch], cut_curve)
env = (1 - np.exp(-t / 0.18)) * np.exp(-t / 0.9)
chord *= env[:, None] * 0.55
place(dry, chord * 0.55, T_DUM + 0.02)
place(hall, chord * 0.35, T_DUM + 0.02)

# ---------------------------------------------------------------- 4. letter ticks (very soft)
for i in range(12):
    t0 = fr(34 + i * 1.6 + 3)
    n = int(0.05 * SR)
    t = tax(n)
    tick = svf_bp(rng.standard_normal(n), np.full(n, 4600.0), q=3) * np.exp(-t / 0.01)
    place(dry, tick * 0.08, t0, pan=-0.6 + 1.2 * i / 11)
    place(hall, tick * 0.08, t0)

# ---------------------------------------------------------------- 5. "zım" – metallic shine (reverse swell -> shing), air sweep L->R
z0, z1 = fr(68), fr(84)
n = int((z1 - z0) * SR)
u = np.linspace(0, 1, n)
air = svf_bp(rng.standard_normal(n), 2500 * (10000 / 2500) ** u, q=1.2) * np.sin(np.pi * u) ** 1.5
place(dry, air * 0.26, z0, pan=np.linspace(-0.9, 0.9, n))
place(hall, air * 0.22, z0)
n = int(0.35 * SR)
t = tax(n)
rev = hp(rng.standard_normal(n), 3000) * (t / t[-1]) ** 3
place(dry, rev * 0.12, T_ZIM - 0.35)
place(hall, rev * 0.2, T_ZIM - 0.35)
n = int(3.0 * SR)
t = tax(n)
zim = np.zeros(n)
for ratio, amp, tau in [(1.0, 1.0, 0.5), (2.005, 0.6, 0.42), (2.76, 0.45, 0.36), (3.99, 0.35, 0.3),
                        (5.41, 0.22, 0.22), (6.8, 0.14, 0.16)]:
    glide = 1 + 0.03 * (1 - np.exp(-t / 0.08))
    zim += amp * osc_sine(1046.5 * ratio * glide) * np.exp(-t / tau)
zim *= np.minimum(t / 0.006, 1) * (1 + 0.12 * np.sin(2 * np.pi * 7 * t))
zst = np.stack([zim * (1 + 0.08 * np.sin(2 * np.pi * 0.9 * t)),
                np.roll(zim, int(0.0007 * SR)) * (1 - 0.08 * np.sin(2 * np.pi * 0.9 * t))], 1)
place(dry, zst * 0.24, T_ZIM)
place(hall, zst * 0.28, T_ZIM)
sub = osc_sine(np.full(n, 41.2)) * np.exp(-t / 0.5) * np.minimum(t / 0.01, 1)
place(dry, sub * 0.22, T_ZIM)

# ---------------------------------------------------------------- 6. heartbeat (tension in the hold)
for t0 in (2.98, 3.22):
    n = int(0.5 * SR)
    t = tax(n)
    hb = osc_sine(52 * (1 + 0.25 * np.exp(-t / 0.03))) * np.exp(-t / 0.09) * np.minimum(t / 0.004, 1)
    hb += lp(rng.standard_normal(n), 120, 4) * np.exp(-t / 0.03) * 0.6
    place(dry, hb * (0.42 if t0 < 3.1 else 0.32), t0)

# ---------------------------------------------------------------- 7. vacuum riser (stops just before the cut)
v0 = fr(108)
v1 = T_CUT - 0.045                      # suck-out gap before the hit
n = int((v1 - v0) * SR)
u = np.linspace(0, 1, n)
amp = u ** 2.2
suck = svf_bp(rng.standard_normal(n), 160 * (5200 / 160) ** u, q=2.2) * amp
tone_f = 55 * (880 / 55) ** (u ** 1.3)
tone = 0.6 * osc_sine(tone_f) + 0.4 * lp(osc_saw(tone_f * 0.5), 2500)
tone *= amp ** 1.3
rate = 0.8 + 10 * u ** 2
pan = 0.7 * np.sin(2 * np.pi * np.cumsum(rate) / SR) * (1 - u ** 3)
fade = np.ones(n)
fade[-int(0.006 * SR):] = np.linspace(1, 0, int(0.006 * SR))
place(dry, suck * fade * 0.85, v0, pan=pan)
place(dry, tone * fade * 0.24, v0, pan=-pan * 0.5)
place(hall, suck * fade * 0.25, v0)

# ---------------------------------------------------------------- 8. CUT TO BLACK – trailer "braam" hit
n = int(2.2 * SR)
t = tax(n)
subdrop = osc_sine(30 + 34 * np.exp(-t / 0.35)) * np.exp(-t / 1.1) * np.minimum(t / 0.002, 1)
braam = np.zeros((n, 2))
for i_, (f, a) in enumerate([(55.0, 1.0), (82.4, 0.7), (110.0, 0.8), (130.8, 0.45), (164.8, 0.3)]):
    for ch, det in enumerate((-0.007, 0.007)):
        braam[:, ch] += a * osc_saw(np.full(n, f * (1 + det)), phase=rng.random())
bc = 180 + 2400 * np.exp(-t / 0.35)
for ch in range(2):
    braam[:, ch] = tv_lowpass(braam[:, ch], bc)
braam = np.tanh(braam * 1.8) * (np.exp(-t / 0.9) * np.minimum(t / 0.012, 1))[:, None]
metal = np.zeros(n)
for f, a, d in [(412, 1.0, 0.5), (1131, 0.6, 0.35), (1873, 0.4, 0.25), (2711, 0.25, 0.18)]:
    metal += a * osc_sine(np.full(n, f)) * np.exp(-t / d)
metal += svf_bp(rng.standard_normal(n), np.full(n, 3200.0), q=1.0) * np.exp(-t / 0.05) * 1.5
metal *= np.minimum(t / 0.001, 1)
crack = hp(rng.standard_normal(n), 900, 2) * np.exp(-t / 0.012)
place(dry, subdrop * 1.0, T_CUT)
place(dry, braam * 0.42, T_CUT)
place(dry, metal * 0.16, T_CUT)
place(dry, crack * 0.35, T_CUT)
place(cave, braam * 0.30, T_CUT)
place(cave, (metal * 0.15 + crack * 0.2), T_CUT)

# ---------------------------------------------------------------- mix
ir_h = reverb_ir(1.8, 0.45)
ir_c = reverb_ir(4.0, 1.1, predelay=0.03, bright=3500)
wet_h = np.stack([signal.fftconvolve(hall[:, c], ir_h[:, c])[:N] for c in range(2)], 1)
wet_c = np.stack([signal.fftconvolve(cave[:, c], ir_c[:, c])[:N] for c in range(2)], 1)
mix = dry + 0.32 * wet_h + 0.30 * wet_c
mix = hp(mix, 24, 2)
peak = np.max(np.abs(mix))
mix = mix / peak * 1.35
mix = np.tanh(mix) / np.tanh(1.35)
fade_n = int(0.5 * SR)
mix[-fade_n:] *= np.linspace(1, 0, fade_n)[:, None] ** 2
mix *= 10 ** (-1.0 / 20)
wavfile.write(sys.argv[1], SR, (mix * 32767).astype(np.int16))
print('wrote', sys.argv[1], f'{DUR:.2f}s')
