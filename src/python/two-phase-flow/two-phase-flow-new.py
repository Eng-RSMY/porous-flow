"""
This program solves pressure-driven, time-dependent flow of two phases
through porous media.

Strong form:

    (lambda(s)*K)^(-1)*u + grad(p) = 0
                            div(u) = 0
              ds/dt + u.grad(F(s)) = 0,

where,

    lambda(s) = 1.0/mu_rel*s^2 + (1 - s)^2
         F(s) = k_rw(s)/mu_w/(k_rw(s)/mu_w + k_ro(s)/mu_o)
              = s^2/(s^2 + mu_rel*(1 - s)^2).


One can then can post-calculate the velocity of each phase using the
relation: u_j = - (k_rj(s)/mu_j)*K*grad(p).

Weak form:

Find u, p, s in V, such that,

   (v, (lambda*K)^(-1)*u) - (div(v), p) = - (v, pbar*n)_N       (1)
      (q, div(u)) = 0 or - (grad(q), u) = - (q, ubar.n)_N       (2)
            (r, ds/dt) - (grad(r), F*u) = - (r, F(sbar)*u.n)_N  (3)
                             
for all v, q, r in V'.

Model problem:

 |----4----|
 |         |
 1         2
 |         |
 |----3----|

Initial Conditions:
u(x, 0) = 0
p(x, 0) = 0
s(x, 0) = 0 in \Omega

Boundary Conditions:
p(x, t) = 1 - x on \Gamma_{1, 2, 3, 4}
s(x, t) = 1 on \Gamma_1 if u.n < 0
s(x, t) = 0 on \Gamma_{2, 3, 4} if u.n < 0

Parameters:
mu_rel, Kinv, lmbdainv, F, dt, T

This implementation includes functional forms from the deal.II demo
available at: http://www.dealii.org/6.2.1/doxygen/deal.II/step_21.html
"""

__author__    = "Garth N. Wells (gnw20@cam.ac.uk) and Harish Narayanan (harish@simula.no)"
__date__      = "2010-01-26"
__copyright__ = "Copyright (C) 2010 Garth N. Wells and Harish Narayanan"
__license__   = "GNU GPL Version 3.0"

from dolfin import *

# Computational domain and geometry information
mesh = UnitSquare(16, 16)
n = FacetNormal(mesh)
boundary = MeshFunction("uint", mesh, mesh.topology().dim() - 1)
boundary.set_all(5)
left, right, bottom, top = compile_subdomains(["x[0] == 0.0", "x[0] == 1.0", "x[1] == 0.0", "x[1] == 1.0"])
left.mark(boundary, 1)
right.mark(boundary, 2)
bottom.mark(boundary, 3)
top.mark(boundary, 4)

# Physical parameters, functional forms and boundary conditions
# Relative viscosity of water w.r.t. crude oil
mu_rel = 0.2

# Spatially-varying permeability matrix (inverse)
kinv = Expression("1.0/std::max(exp(-pow((x[1] - 0.5 - 0.1*sin(10*x[0]))/0.1, 2.0)), 0.01)")
zero = Expression("0.0")
Kinv = as_matrix(((kinv, zero), (zero, kinv)))

# Total mobility
def lmbdainv(s):
    return 1.0/((1.0/mu_rel)*s**2 + (1 - s)**2)

# Fractional flow function
def F(s):
    return s**2/(s**2 + mu_rel*(1 - s)**2)

# Time step
dt = 0.01

# Pressure boundary condition
class PressureBC(Expression):
    def eval(self, values, x):
        values[0] = 1.0 - x[0]

# Saturation boundary condition
class SaturationBC(Expression):
    def eval(self, values, x):
        values[0] = 1.0 - x[0]

# Normal velocity boundary condition
class NormalVelocityBC(Expression):
    def eval(self, values, x):
        values[0] = 0.0

# Function spaces
degree = 1
BDM = FunctionSpace(mesh, "BDM", degree)
DG  = FunctionSpace(mesh, "DG",  degree - 1)
CG  = FunctionSpace(mesh, "CG",  degree)
mixed_space = MixedFunctionSpace([BDM, DG, CG])
P1v  = VectorFunctionSpace(mesh, "CG",  1)

# Functions
V   = TestFunction(mixed_space)
dU  = TrialFunction(mixed_space)
U   = Function(mixed_space)
U0  = Function(mixed_space)

v, q, r = split(V)
u, p, s = split(U)
u0, p0, s0 = split(U0)

pbar = PressureBC()
sbar = SaturationBC()
unbar = NormalVelocityBC()

s_mid = 0.5*(s0 + s)

# Variational forms and problem
L1 = inner(v, lmbdainv(s_mid)*Kinv*u)*dx - div(v)*p*dx + inner(v, pbar*n)*ds(1) \
    + inner(v, pbar*n)*ds(2) + inner(v, pbar*n)*ds(3) + inner(v, pbar*n)*ds(4)
a1 = derivative(L1, U, dU)

L2 = q*div(u)*dx
a2 = derivative(L2, U, dU)

epsilon = 0.01
L3 = r*(s - s0)*dx - dt*inner(grad(r), F(s_mid)*u)*dx + dt*r*inner(F(sbar)*u, n)*ds(1) \
    + epsilon*dt*inner(grad(r), grad(s_mid))*dx
a3 = derivative(L3, U, dU)

# FIXME: The stabilisation term above should look like the following
#
# Upwind normal velocity: (dot(v, n) + |dot(v, n)|)/2.0 
# (using velocity from previous step on facets)
# un   = (dot(u0, n) + sqrt(dot(u0, n)*dot(u0, n)))/2.0
# un_h = (dot(u0, n) - sqrt(dot(u0, n)*dot(u0, n)))/2.0
# epsilon = 1.0
#
# stabilisation = dt*inner(jump(r), un('+')*F(s_mid)('+') - un('-')*F(s_mid)('-'))*dS

L = L1 + L2 + L3
a = a1 + a2 + a3

problem = VariationalProblem(a, L, exterior_facet_domains=boundary, nonlinear=True)

u_file = File("velocity.pvd")
p_file = File("pressure.pvd")
s_file = File("saturation.pvd")

t = 0.0
T = 200*dt
while t < T:
    t += dt
    U0.assign(U)
    problem.solve(U)
    u, p, s = U.split() 
    uh = project(u, P1v)
#    plot(uh, title="Velocity")
#    plot(p, title="Pressure")
#    plot(s, title="Saturation")
    
    u_file << uh
    p_file << p
    s_file << s
