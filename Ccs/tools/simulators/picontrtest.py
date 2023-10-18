import matplotlib.pyplot as plt
import numpy as np
import sys

sys.path.insert(0, '../..')
import thermal_control as tmc
import thermal_model as tmo

T_REF = -116.
PI_ALGO = 1

OFFSET = 30
COEFFP = 50
COEFFI = 0.001
EXEC_PER = 40

MODSTEP = 5

save = 0
sufx = '_addheat'
showpwr = 1

mod = tmo.ThermalModel(-125, record=True, step=MODSTEP)
mod.sigma_T = 0.0005
mod.mass = 3.
mod.rad_area = .25
mod.T0 = -125
mod.t_l = 60
mod.t_d = 5

mod.set_delay_func(tmo.sigmoid)
# plt.plot(mod.heat_distr)

tctrl = tmc.ThermalController(T_REF, COEFFP, COEFFI, OFFSET, EXEC_PER, model=mod, pi=PI_ALGO, deltaTmax=1)
tctrl.MAXDELTAVOLTAGE = 0.2

hours = 42
NCTRLSTEPS = int(hours * 3600 / (EXEC_PER / 8))  # int(sys.argv[2])
modstepsperctrl = int(EXEC_PER / 8 / MODSTEP)

print('run thctrl for {} steps, with {} s period ({} s)'.format(NCTRLSTEPS, EXEC_PER / 8, NCTRLSTEPS * EXEC_PER / 8))
print('{} model iterations per control step'.format(modstepsperctrl))

simlog = []
t = 0
TINIT = mod.T0
Toffset = 0
glitches = ()#tmo.rng.choice(range(NCTRLSTEPS), 10)
drift = 1

for i in range(NCTRLSTEPS):
    for j in range(modstepsperctrl):
        mod.evolve(t)
        t += MODSTEP

    # insert T glitches at random positions
    if i in glitches:
        if i % 2:
            tctrl._step(t, with_model=True, glitch=20)
        else:
            tctrl._step(t, with_model=True, glitch=-20)
    else:
        tctrl._step(t, with_model=True, glitch=Toffset)

    # sudden T offset for some time
    # if int(t) == 40000:
    #     print(t)
    #     mod.inst_heat = 2.5
    # if int(t) == 80000:
    #     print(t)
    #     mod.inst_heat = 1
    # if int(t) == 100000:
    #     print(t)
    #     mod.inst_heat = 0

    # if int(t) == 50000:
    #     print(t)
    #     Toffset = 2
    #
    # if int(t) == 51800:
    #     print(t)
    #     Toffset = 0

    if i % 1000 == 0:
        print(i, 'steps of', NCTRLSTEPS)

    # drift in equilibrium temperature
    if drift:
        mod.T0 = TINIT * (1 - 0.05 * np.cos(1 * i * 2 * np.pi / NCTRLSTEPS))

    simlog.append((t, mod.T0, mod.T, mod.htr_pwr, mod.inst_heat))

simlog = np.array(simlog).T
print(mod.T0)

r = np.array(tctrl.log).T
mr = np.array(mod.log).T

if not showpwr:
    fig, ax = plt.subplots(2, 1, sharex=True, gridspec_kw={'height_ratios': [2, 1]}, figsize=(10, 6))
    ax1, ax2 = ax

    ax1.plot(r[0], r[2], color='tab:blue', label='$T$')
    ax1.axhline(T_REF, c='grey', ls='--', label=r'$T_\mathrm{ref}$')
    ax1.tick_params(bottom=False)
    ax1.set_ylim((-118, -114))
    ax1.grid()
    # ax1.plot(simlog[0], simlog[2], color='tab:pink', ls='--', alpha=1, label=r'$T_\mathrm{act}$')
    ax1.set_ylabel('temperature [°C]')
    ax1.legend()
    ax2.plot(r[0], r[3], color='tab:orange', label=r'$V_\mathrm{ctrl}$')
    ax2.set_xlabel('time [s]')
    ax2.set_ylabel(r'$U_\mathrm{ctrl}$ [V]')
    ax2.set_ylim((0, 3))
    ax2.grid()
else:
    fig, ax = plt.subplots(4, 1, sharex=True, gridspec_kw={'height_ratios': [2, 1, 1, 1]}, figsize=(12, 9))
    ax1, ax2, ax3, ax4 = ax

    ax1.plot(r[0], r[2], color='tab:blue', label='$T$')
    ax1.plot(simlog[0], simlog[2], color='blue', alpha=.2, label=r'$T_\mathrm{mod}$')
    ax1.axhline(T_REF, c='grey', ls='--', label=r'$T_\mathrm{ref}$')
    ax1.tick_params(bottom=False)
    ax1.set_ylim((-118, -114))
    ax1.grid()
    ax11 = ax1.twinx()
    ax11.set_ylabel('$T_0$ [°C]', color='tab:green')
    ax11.plot(simlog[0], simlog[1], color='tab:green', ls='--', alpha=0.5)
    ax11.tick_params(axis='y', colors='tab:green')
    ax1.set_ylabel('temperature [°C]')
    ax1.legend()
    ax2.plot(r[0], r[3], color='tab:orange', label=r'$V_\mathrm{ctrl}$')
    ax2.set_ylabel(r'$U_\mathrm{ctrl}$ [V]')
    ax2.set_ylim((0, 3))
    ax2.tick_params(bottom=False)
    ax2.grid()
    ax3.plot(simlog[0], simlog[3], color='tab:red', ls='--', alpha=1, label='htr')
    ax3.plot(simlog[0], simlog[4], color='tab:purple', ls='--', alpha=1, label='inst')
    ax3.plot(mr[0], mr[3], color='tab:cyan', ls='--', alpha=1, label='cool')
    ax3.set_ylabel('$P$ [W]')
    ax3.set_ylim((-1, 10))
    ax3.tick_params(bottom=False)
    ax3.grid()
    ax3.legend()
    if PI_ALGO:
        ax4.axhline(OFFSET, color='tab:brown', label='O', zorder=0)
        ax4.plot(r[0], r[5], color='tab:pink', label='P', zorder=2)
        ax4.plot(r[0], r[4], color='tab:olive', label='I', zorder=1)
        ax4.legend()
    ax4.set_ylabel('percentage')
    ax4.set_xlabel('time [s]')
    ax4.grid()

plt.tight_layout()
fig.subplots_adjust(hspace=0.075)

if save:
    plt.savefig('/home/marko/space/smile/OBSW/Documentation/htrctrlsim/picrtl_sim_{:.0f}s_p{:d}_i{:.5f}{}.pdf'.format(EXEC_PER / 8, COEFFP, COEFFI, sufx))
    plt.savefig('/home/marko/space/smile/OBSW/Documentation/htrctrlsim/picrtl_sim_{:.0f}s_p{:d}_i{:.5f}{}.png'.format(EXEC_PER / 8, COEFFP, COEFFI, sufx), dpi=200)

plt.show()

# tctrl.save_log(fname)
# print('END, data saved to {}'.format(fname), time.time())
