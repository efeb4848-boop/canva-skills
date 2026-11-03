"""Alyans Dental intro – ses tasarımı (48 kHz stereo, tamamen sentez).
Kullanım: python sfx.py out.wav
Zamanlama, scene.py içindeki kare zaman çizelgesiyle eşleşir (30 fps)."""
import sys
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
FPS = 30
DUR = 165 / FPS
N = int(DUR * SR)
rng = np.random.default_rng(11)


def fr(f):
    """frame number -> seconds (frame 1 == t 0)"""
    return (f - 1) / FPS


def t_axis(n):
    return np.arange(n) / SR


def env_adsr(n, a, d_tau, hold=0.0):
    t = t_axis(n)
    e = np.where(t < a, t / max(a, 1e-6), np.exp(-(t - a - hold).clip(0) / d_tau))
    return e


def place(bus, x, t0, gain=1.0, pan=0.0):
    """mix mono or stereo x into stereo bus at t0 seconds; pan -1..1 (const power)"""
    i0 = int(round(t0 * SR))
    if x.ndim == 1:
        if np.isscalar(pan):
            pan = np.full(len(x), pan)
        th = (np.asarray(pan) + 1) * np.pi / 4
        x = np.stack([x * np.cos(th), x * np.sin(th)], 1)
    i1 = min(len(bus), i0 + len(x))
    if i1 > i0 >= 0:
        bus[i0:i1] += gain * x[:i1 - i0]


def bandpass_sweep(noise, f_start, f_end, q=2.0, shape='exp'):
    """time-varying band-pass via state-variable filter"""
    n = len(noise)
    if shape == 'exp':
        fc = f_start * (f_end / f_start) ** np.linspace(0, 1, n)
    else:
        fc = shape(np.linspace(0, 1, n))
    out = np.zeros(n)
    low = band = 0.0
    damp = 1.0 / q
    f = 2 * np.sin(np.pi * np.minimum(fc, SR / 6) / SR)
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


def sine_sweep(n, f0, f1, curve='exp'):
    if curve == 'exp':
        f = f0 * (f1 / f0) ** np.linspace(0, 1, n)
    else:
        f = np.linspace(f0, f1, n)
    return np.sin(2 * np.pi * np.cumsum(f) / SR), f


def reverb_ir(seconds=1.8, decay=0.55, predelay=0.012):
    n = int(seconds * SR)
    t = t_axis(n)
    ir = rng.standard_normal((n, 2)) * np.exp(-t / decay)[:, None]
    ir = lp(ir, 7000)
    # diffuse, slightly darker tail
    ir[:, 0] *= np.exp(-t / (decay * 1.05)) / np.exp(-t / decay)
    pd = int(predelay * SR)
    ir = np.concatenate([np.zeros((pd, 2)), ir])
    return ir / np.sqrt(np.sum(ir ** 2) / 2)


dry = np.zeros((N, 2))
send = np.zeros((N, 2))      # reverb send

# ---------------------------------------------------------------- 1. atmosphere riser (0 -> landing)
land = fr(38)
n = int((land + 0.02) * SR)
t = t_axis(n)
nz = rng.standard_normal(n)
riser = bandpass_sweep(nz, 180, 5200, q=1.4)
riser *= (t / t[-1]) ** 2.6
drone = (np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 82.4 * t) + 0.25 * np.sin(2 * np.pi * 110 * t))
drone *= np.minimum(t / 0.5, 1) * 0.5 * (0.6 + 0.4 * t / t[-1])
place(dry, riser * 0.22, 0.0, pan=np.linspace(-0.3, 0.2, n))
place(send, riser * 0.25, 0.0)
place(dry, drone * 0.10, 0.0)

# ---------------------------------------------------------------- 2. whoosh – mark flies in from upper-left
w0, w1 = fr(8), fr(37)
n = int((w1 - w0 + 0.25) * SR)
u = np.linspace(0, 1, n)
nz = rng.standard_normal(n)
fc = lambda s: 350 + 2600 * np.sin(np.pi * np.clip(s * 1.05, 0, 1)) ** 2
wh = bandpass_sweep(nz, 0, 0, q=1.8, shape=fc)
whenv = np.exp(-((u - 0.78) / 0.24) ** 2)
wh *= whenv
place(dry, wh * 0.55, w0, pan=np.linspace(-0.85, 0.05, n))
place(send, wh * 0.35, w0)

# ---------------------------------------------------------------- 3. landing impact
n = int(2.6 * SR)
t = t_axis(n)
boom, _ = sine_sweep(n, 72, 36)
boom *= np.exp(-t / 0.42) * np.minimum(t / 0.004, 1)
thud = lp(rng.standard_normal(n), 260, 4) * np.exp(-t / 0.06)
click = hp(rng.standard_normal(n), 3000) * np.exp(-t / 0.004)
imp = 0.9 * boom + 0.9 * thud + 0.25 * click
place(dry, imp * 0.85, land)
place(send, imp * 0.35, land)

# ---------------------------------------------------------------- 4. letter ticks (soft, panned L->R)
for i in range(12):
    t0 = fr(34 + i * 1.6 + 3)
    n = int(0.06 * SR)
    t = t_axis(n)
    tick = bandpass_sweep(rng.standard_normal(n), 5200, 3800, q=3) * np.exp(-t / 0.012)
    place(dry, tick * 0.16, t0, pan=-0.6 + 1.2 * i / 11)
    place(send, tick * 0.12, t0)

# ---------------------------------------------------------------- 5. tagline shimmer
s0 = fr(50)
n = int(0.9 * SR)
t = t_axis(n)
sh = np.zeros(n)
for k, f in enumerate([2637, 3136, 3951, 4699]):
    sh += np.sin(2 * np.pi * f * t + k) * (0.5 + 0.5 * np.sin(2 * np.pi * (5 + k) * t))
sh *= np.sin(np.pi * np.clip(t / 0.9, 0, 1)) ** 2 * 0.25
air = hp(rng.standard_normal(n), 6000) * np.sin(np.pi * t / 0.9) ** 2 * 0.25
place(dry, (sh + air) * 0.18, s0, pan=0.0)
place(send, (sh + air) * 0.25, s0)

# ---------------------------------------------------------------- 6. "ZIM" – light sweep (metallic shing + air sweep L->R)
z0, z1 = fr(68), fr(84)
n = int((z1 - z0) * SR)
u = np.linspace(0, 1, n)
air = bandpass_sweep(rng.standard_normal(n), 2500, 11000, q=1.2) * np.sin(np.pi * u) ** 1.5
place(dry, air * 0.35, z0, pan=np.linspace(-0.9, 0.9, n))
place(send, air * 0.3, z0)

zt = fr(72)     # the "zım" hit lands while the band crosses the mark
n = int(3.0 * SR)
t = t_axis(n)
zim = np.zeros(n)
base = 1318.5
for ratio, amp, tau in [(1.0, 1.0, 0.5), (2.005, 0.6, 0.42), (2.76, 0.45, 0.36), (3.99, 0.35, 0.3),
                        (5.41, 0.22, 0.22), (6.8, 0.14, 0.16)]:
    glide = 1 + 0.03 * (1 - np.exp(-t / 0.08))
    ph = 2 * np.pi * np.cumsum(base * ratio * glide) / SR
    zim += amp * np.sin(ph) * np.exp(-t / tau)
zim *= np.minimum(t / 0.006, 1)
trem = 1 + 0.15 * np.sin(2 * np.pi * 7 * t)
zim *= trem
zl = zim * (1 + 0.08 * np.sin(2 * np.pi * 0.9 * t))
zr = np.roll(zim, int(0.0007 * SR)) * (1 - 0.08 * np.sin(2 * np.pi * 0.9 * t))
zst = np.stack([zl, zr], 1)
place(dry, zst * 0.30, zt)
place(send, zst * 0.30, zt)

# sparkle "ting" when the star pops on the tip
st = fr(80)
n = int(1.4 * SR)
t = t_axis(n)
ting = (np.sin(2 * np.pi * 4186 * t) * np.exp(-t / 0.35) + 0.6 * np.sin(2 * np.pi * 6272 * t) * np.exp(-t / 0.22)
        + 0.3 * np.sin(2 * np.pi * 8372 * t) * np.exp(-t / 0.12)) * np.minimum(t / 0.002, 1)
place(dry, ting * 0.16, st, pan=0.45)
place(send, ting * 0.22, st)

# ---------------------------------------------------------------- 7. vacuum suction (breath -> suck, swirling pan)
v0, v1 = fr(110), fr(136)
n = int((v1 - v0) * SR)
u = np.linspace(0, 1, n)
t = t_axis(n)
amp = u ** 2.4
suck = bandpass_sweep(rng.standard_normal(n), 160, 4800, q=2.2) * amp
tone, fsw = sine_sweep(n, 70, 980)
saw = signal.sawtooth(2 * np.pi * np.cumsum(fsw * 0.5) / SR)
tone = 0.6 * tone + 0.4 * lp(saw, 2500)
tone *= amp ** 1.3
swirl_rate = 0.8 + 9 * u ** 2
pan = 0.7 * np.sin(2 * np.pi * np.cumsum(swirl_rate) / SR) * (1 - u ** 3)
place(dry, suck * 0.95, v0, pan=pan)
place(dry, tone * 0.22, v0, pan=-pan * 0.5)
place(send, suck * 0.4, v0)
# breath (tiny inhale before the suck)
n = int(0.32 * SR)
t = t_axis(n)
inh = bandpass_sweep(rng.standard_normal(n), 700, 1600, q=1.5) * np.sin(np.pi * t / t[-1]) ** 2
place(dry, inh * 0.20, fr(108))

# ---------------------------------------------------------------- 8. "ÇIK" – pop / click close
pt = fr(136)
n = int(1.2 * SR)
t = t_axis(n)
pop_tone, _ = sine_sweep(n, 1500, 260)
pop_tone *= np.exp(-t / 0.045)
clk = hp(rng.standard_normal(n), 2500, 4) * np.exp(-t / 0.0025)
thump, _ = sine_sweep(n, 95, 44)
thump *= np.exp(-t / 0.16) * np.minimum(t / 0.002, 1)
snap = bandpass_sweep(rng.standard_normal(n), 3200, 1200, q=2.5) * np.exp(-t / 0.018)
popx = 0.8 * pop_tone + 0.6 * clk + 1.0 * thump + 0.5 * snap
place(dry, popx * 0.95, pt - 0.004)
place(send, popx * 0.55, pt)

# ---------------------------------------------------------------- mix
ir = reverb_ir(1.9, 0.5)
wet = np.stack([signal.fftconvolve(send[:, c], ir[:, c])[:N] for c in range(2)], 1)
mix = dry + 0.38 * wet
mix = hp(mix, 28, 2)
# gentle bus compression-ish soft clip and normalisation
peak = np.max(np.abs(mix))
mix = mix / peak * 1.25
mix = np.tanh(mix) / np.tanh(1.25)
# final fade so the tail ends cleanly on black
fade_n = int(0.35 * SR)
mix[-fade_n:] *= np.linspace(1, 0, fade_n)[:, None] ** 2
mix *= 10 ** (-1.0 / 20)
wavfile.write(sys.argv[1], SR, (mix * 32767).astype(np.int16))
print('wrote', sys.argv[1], f'{DUR:.2f}s')
