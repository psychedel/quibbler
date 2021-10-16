from pyquibbler import iquib, override_all, q, quibbler_user_function
from pyquibbler.quib.assignment import RangeAssignmentTemplate
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib import widgets
import numpy as np

override_all()

# Total time (sec):
total_time = iquib(100);

# Number of time points (limited to even numbers between 0 and 1000):
num_time_points = iquib(300, assignment_template=RangeAssignmentTemplate(start=0, stop=1000, step=2));

# Time vector:
t = np.linspace(0, total_time, num_time_points);

# Period (sec):
period = iquib(10);
w = 2 * np.pi / period;

# Type of functions:
nSin = iquib(3, assignment_template=RangeAssignmentTemplate(start=1, stop=13, step=2));
signal_fnc_list = ['sin', 'square', 'triangle', 'sin^n']
signal_fnc_chosen = iquib(1);


# Signal as a function of time:
@quibbler_user_function(True)
def get_signal(t, w, chosen, n):
    signal_sin = np.sin(w * t);
    if chosen == 0:
        return signal_sin
    elif chosen == 1:
        return (signal_sin > 0) * 2 - 1
    elif chosen == 2:
        return np.arcsin(signal_sin)
    elif chosen == 3:
        return signal_sin ** n;
    else:
        assert (False)


signal = get_signal(t, w, signal_fnc_chosen, nSin);

# Add Noise:
noise_amp = iquib(0);
noise = noise_amp * np.random.randn(num_time_points);

measurement = signal + noise;

# Bandwidth:
min_freq = iquib(0);
max_freq = iquib(0.6);

# FFT:
spectrum = q(np.fft.fft, measurement);
dfreqs = 1 / total_time;  # Frequency resolution
freqs = np.concatenate(
    [np.arange(0, (num_time_points - 1) / 2), np.arange(num_time_points / 2, 0, -1)]) * dfreqs  # Frequency vector

# Apply band filter
spectrum_filtered = spectrum * ((freqs >= min_freq) & (freqs <= max_freq));

# Inverse FFT:
S0 = q(np.fft.ifft, spectrum_filtered);

# figure setup:
fig = plt.figure(1,figsize=(6,8))

# signal vs time
fig.clf()
axs1 = fig.add_axes((0.15,0.78,0.75,0.2))
axs1.set_ylim([np.min(measurement)-0.5-noise_amp, np.max(measurement)+0.5+noise_amp])
axs1.set_xlim([0,total_time])
axs1.set_xlabel('Time (sec)')
axs1.set_ylabel('Signal')
axs1.plot(t,np.real(S0), '.-', color=[0,0.7,0])
axs1.plot(t,np.real(measurement), '.-', color=[0.8,0,0]);

# spectrum
axs2 = fig.add_axes((0.15,0.5,0.75,0.2))
yl = np.max(np.abs(spectrum))*1.1
axs2.axis([-dfreqs,np.max(freqs)+dfreqs,0,yl])
axs2.set_xlabel('Frequency (1/sec)')
axs2.set_ylabel('Amplitude')
axs2.plot(freqs,np.abs(spectrum),'r.-')
axs2.plot(freqs,np.abs(spectrum_filtered),'g.-')
axs2.plot(min_freq,0,'k^',markersize=18, picker=True)
axs2.plot(max_freq,0,'k^',markersize=18, picker=True)

# sliders of quibs:
slider_axs = [fig.add_axes([0.3,0.2-i*0.04,0.5,0.02]) for i in range(5)]
widgets.Slider(ax=slider_axs[0], label='Number of points', valmin=1, valmax=1000, valstep=2,   valinit=num_time_points)
widgets.Slider(ax=slider_axs[1], label='Period',           valmin=0, valmax=20,   valstep=1,   valinit=period)
widgets.Slider(ax=slider_axs[2], label='Total time',       valmin=0, valmax=200,  valstep=5,   valinit=total_time)
widgets.Slider(ax=slider_axs[3], label='Noise amplitude',  valmin=0, valmax=2,    valstep=0.1, valinit=noise_amp)
widgets.Slider(ax=slider_axs[4], label='Power of sin',     valmin=1, valmax=19,   valstep=1,   valinit=nSin);

# Make the 'Power of sin' slider visible only when signal_fnc_chosen==3:
is_sinN = q(lambda x:x==3,signal_fnc_chosen)
a = slider_axs[4].set_visible(is_sinN)

# radio buttons to choose function:
axs_radio = fig.add_axes([0.3,0.25,0.5,0.14])
btns = widgets.RadioButtons(
    ax=axs_radio, labels=signal_fnc_list, active=signal_fnc_chosen)

plt.show()