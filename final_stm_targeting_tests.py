import numpy as np
import scipy as sp
from scipy import integrate
from sympy import *
from mpmath import *
import CombinedModelJacobian as CJJacobian
import TargetingUtils

r_e = 6378136.3
j2 = 1.082E-3
mu = 3.986004415E14
a_reference = 6378136.3 + 300000
inc_reference = 30 * np.pi / 180
k_j2 = 3*j2*mu*r_e**2 / 2


def velocity_from_state(wy, wz, r_reference, v_z, x, y, z, p1, p2, p3):
    vx = p1 + y*wz - (z - r_reference)*wy
    vy = p2 - x*wz
    vz = p3 - v_z + x*wy
    return [vx, vy, vz]


def combined_model_eom(t, state, A, c_d, a_m_reference, a_m_chaser, r_0, rho_0, H):

    # <- r_reference, v_z, h_reference, theta_reference, i_reference, x_0, y_0, z_0, p1, p2, p3
    S_T = TargetingUtils.recompose(state, len(A[0]))
    S_T_dt = np.matmul(A(state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7], state[8], state[9], state[10]), S_T)
    wy = -state[2] / state[0]**2
    wz = k_j2 * np.sin(2*state[4]) * np.sin(state[3]) / (state[2] * state[0]**3)

    r_chaser = np.linalg.norm([state[5], state[6], state[7] - state[0]])
    z_chaser = state[5]*np.cos(state[3])*np.sin(state[4]) - state[6]*np.cos(state[4]) - (state[7] - state[0])*np.sin(state[4])*np.sin(state[3])
    w_bar = -mu / r_chaser**3 - k_j2 / r_chaser**5 + 5*k_j2*z_chaser**2 / r_chaser**7
    zeta = 2*k_j2*z_chaser / r_chaser**5

    v_reference = np.linalg.norm([state[2]/state[0], 0, state[1]])
    rho_reference = rho_0*np.exp(-(state[0] - r_0)/H)
    f_drag_reference = - .5*c_d*a_m_reference*rho_reference

    dstate_dt = np.asarray([])

    dstate_dt[0] = -state[1]  # d r / dt
    dstate_dt[1] = mu / state[0]**2 - state[2]**2 / state[0]**3 + k_j2*(1 - 3*np.sin(state[4])**2 * np.sin(state[3])**2) / state[0]**4 + f_drag_reference*state[1]*v_reference  # d v_z / dt
    dstate_dt[2] = -k_j2*np.sin(state[4])**2*np.sin(2*state[3]) / state[0]**3  # d h_reference / dt
    dstate_dt[3] = state[2] / state[0]**2 + 2*k_j2*np.cos(state[4])**2*np.sin(state[3])**2 / (state[2] * state[0]**3)  # d theta_reference / dt
    dstate_dt[4] = -k_j2*np.sin(2*state[3])*np.sin(2*state[4]) / (2 * state[2] * state[0]**3)  # d i_reference / dt
    dstate_dt[5] = state[8] + state[6]*wz - (state[7] - state[0])*wy  # d x / dt
    dstate_dt[6] = state[9] - state[5]*wz  # d y / dt
    dstate_dt[7] = state[10] - state[1] + state[5]*wy  # d z / dt

    v_chaser = [dstate_dt[5] - state[6]*wz + (state[7] - state[0])*wy, dstate_dt[6] + state[5]*wz, dstate_dt[7] + state[1] - state[5]*wy]
    rho_chaser = rho_0*np.exp(-(r_chaser - r_0)/H)
    f_drag_chaser = - .5*c_d*a_m_chaser*rho_chaser*np.linalg.norm(v_chaser)

    dstate_dt[8] = w_bar*state[5] - zeta*np.cos(state[3])*np.sin(state[4]) + state[9]*wz - state[10]*wy + f_drag_chaser*v_chaser[0]  # d p1 / dt
    dstate_dt[9] = w_bar*state[6] + zeta*np.cos(state[4]) - state[8]*wz + f_drag_chaser*v_chaser[1]  # d p2 / dt
    dstate_dt[10] = w_bar*(state[7] - state[0]) + zeta*np.sin(state[3])*np.sin(state[4]) + state[8]*wy + f_drag_chaser*v_chaser[2]  # d p3 / dt

    dstate_dt = np.concatenate((dstate_dt, S_T_dt), axis=0).flatten()

    return dstate_dt


def combined_targeter(time, delta_state_0, step, targeted_state, target, c_d, a_m_reference, a_m_chaser, r_0, rho_0, H):

    # compute constants for reuse in targeting at time t=0
    # some variables are assigned from the initial state vector for clarity's sake
    wy_0 = -delta_state_0[2] / delta_state_0[0] ** 2
    wz_0 = k_j2 * np.sin(2 * delta_state_0[4]) * np.sin(delta_state_0[3]) / (delta_state_0[2] * delta_state_0[0] ** 3)
    r_reference_0 = delta_state_0[0], v_z_0 = delta_state_0[1]
    x_0 = delta_state_0[5], y_0 = delta_state_0[6], z_0 = delta_state_0[7]
    p1_0 = delta_state_0[8], p2_0 = delta_state_0[9], p3_0 = delta_state_0[10]
    v_0 = velocity_from_state(wy_0, wz_0, r_reference_0, v_z_0, x_0, y_0, z_0, p1_0, p2_0, p3_0)

    # Jacobian matrix
    A = CJJacobian.get_jacobian(c_d, a_m_reference, a_m_chaser, r_0, rho_0, H)

    sc = sp.integrate.ode(
        lambda t, x: combined_model_eom(t, x, A, c_d, a_m_reference, a_m_chaser, r_0, rho_0, H)).set_integrator('dopri5',
                                                                                                        atol=1e-10,
                                                                                                        rtol=1e-5)
    sc.set_initial_value(delta_state_0, time[0])

    t = np.zeros((len(time)+1))
    result = np.zeros((len(time)+1, len(delta_state_0)))
    t[0] = time[0]
    result[0][:] = delta_state_0

    step_count = 1
    target_status = True
    stable = True
    d_v = [0, 0, 0]

    if target:
        while sc.successful() and stable:
            sc.integrate(sc.t + step)
            # Store the results to plot later
            t[step_count] = sc.t
            result[step_count][:] = sc.y
            step_count += 1

            if step_count > len(t) - 1 and target:
                S_T = TargetingUtils.recompose(sc.y, 6)
                S_T_rv_vv = Matrix(S_T[np.arange(0, 6)[:, None], np.arange(3, 6)[None, :]])
                initial_d_dv1, initial_d_dv2, initial_d_dv3 = symbols('initial_d_dv1 initial_d_dv2 initial_d_dv3',
                                                                      real=True)
                initial_d_dv = Matrix([initial_d_dv1, initial_d_dv2, initial_d_dv3])
                S_T_times_initial_d_dv = S_T_rv_vv * initial_d_dv
                final_d_dp = np.asarray(targeted_state) - sc.y[:3]

                eqs = [S_T_times_initial_d_dv[0] - final_d_dp[0],
                       S_T_times_initial_d_dv[1] - final_d_dp[1],
                       S_T_times_initial_d_dv[2] - final_d_dp[2]]

                reeeeee = linsolve(eqs, initial_d_dv1, initial_d_dv2, initial_d_dv3).args[0]
                d_v = [reeeeee[0], reeeeee[1], reeeeee[2]]  # reference - actual

                target_status = False
                stable = False

            elif step_count > len(t) - 1 and not target:
                stable = False

    elif not target:
        while sc.successful() and stable and step_count < len(t):
            sc.integrate(sc.t + step)
            # Store the results to plot later
            t[step_count] = sc.t
            result[step_count][:] = sc.y
            step_count += 1

    return t, result, target_status, stable, d_v


def main():
    return


if __name__ == "__main__":
    main()
