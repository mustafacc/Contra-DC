""" 
    Class ChripedContraDC_v4.py
    
    Chirped contra-directional coupler model
    Chirp your CDC, engineer your response
    (Or let a computer engineer it for you)
    
    Based on Matlab model by Jonathan St-Yves
    as well as Python model by Mustafa Hammood

    Jonathan Cauchon, September 2019

    -- v4 novelties --
    - corrections for chirp profiles that were not uniform
    - Turned self.performance to a dict
    - added user-friendly unit getters for easier unit conversion


"""

"""   Notes
- Experimental vs simulated:
    Center wavelength: experimental is 8 nm higher than simulated center wvl

"""
import numpy as np
from modules import *
from utils import *

def clc():
    print ("\n"*10)


class ChirpedContraDC():
    def __init__(self, N = 1000, period = 322e-9, a = 12, apod_shape = "gaussian",  \
        kappa = 48000, T = 300, resolution = 300, N_seg = 50, wvl_range = [1530e-9,1580e-9],  \
        central_wvl = 1550e-9, alpha = 10, stages = 1, w1 = .56e-6, w2 = .44e-6, target_wvl = None, \
        w_chirp_step = 1e-9, period_chirp_step = 2e-9):

        # Class attributes
        self.N           =  N           #  int    Number of grating periods      [-]
        self.period      =  period      #  float  Period of the grating          [m]
        self.a           =  a           #  int    Apodization Gaussian constant  [-]
        self.kappa       =  kappa       #  float  Maximum coupling power         [m^-1]
        self.T           =  T           #  float  Device temperature             [K]
        self.resolution  =  resolution  #  int    Nb. of freq. points computed   [-]
        self.N_seg       =  N_seg       #  int    Nb. of apod. & chirp segments  [-]
        self.alpha       =  alpha       #  float  Propagation loss grating       [dB/cm]
        self.stages      =  stages      #  float  Number of cascaded devices     [-]
        self.wvl_range   =  wvl_range   #  list   Start and end wavelengths      [m]
        self.w1          =  w1          #  float  Width of waveguide 1           [m]
        self.w2          =  w2          #  float  Width of waveguide 2           [m]
        self.target_wvl  =  target_wvl  #  list   Targeted reflection wavelength range [m]
        self.apod_shape  =  apod_shape  #  string described the shape of the coupling apodization []

        self.period_chirp_step = period_chirp_step # To comply with GDS resolution
        self.w_chirp_step = w_chirp_step

        # Note that gap is set to 100 nm

        # Constants
        self._antiRefCoeff = 0.01
        

        # Properties that will be set through methods
        self.apod_profile = None
        self.period_profile = None
        self.w1_profile = None
        self.w2_profile = None
        self.T_profile = None

        # Useful flag
        self.is_simulated = False

        
        # Dictionary conatining all units relative to the model
        self.units = {
                    "N"           :  None,   
                    "period"      :  "m",
                    "a"           :  None,       
                    "kappa"       :  "1/mm",   
                    "T"           :  "K",       
                    "resolution"  :  None,
                    "N_seg"       :  None,    
                    "alpha"       :  "dB/cm",    
                    "stages"      :  None,   
                    "wvl_range"   :  "m", 
                    "width"       :  "m",      #  
                    "target_wvl"  :  "m",
                    "apod_shape"  :  None,
                    "group delay" :  "s" }

    # return properties in user-friendly units
    @property
    def _wavelength(self):
        return self.wavelength*1e9

    @property
    def _period(self):
        return np.asarray(self.period)*1e9

    @property
    def _kappa(self):
        return self.kappa*1e-3

    @property
    def _apod_profile(self):
        return self.apod_profile*1e-3

    @property
    def _w1(self):
        return np.asarray(self.w1)*1e9  

    @property
    def _w2(self):
        return np.asarray(self.w2)*1e9

    @property
    def _period_profile(self):
        return self.period_profile*1e9

    @property
    def _w1_profile(self):
        return self.w1_profile*1e9  

    @property
    def _w2_profile(self):
        return self.w2_profile*1e9

    # Other non-changing properties
    @property
    def wavelength(self):
        return np.linspace(self.wvl_range[0], self.wvl_range[1], self.resolution)

    @property
    def c(self):
        return 299792458

    @property
    def l_seg(self):
        return self.N*np.mean(self.period)/self.N_seg
    

    # linear algebra numpy manipulation functions
    def switchTop(self, P):
        P_FF = np.asarray([[P[0][0],P[0][1]],[P[1][0],P[1][1]]])
        P_FG = np.asarray([[P[0][2],P[0][3]],[P[1][2],P[1][3]]])
        P_GF = np.asarray([[P[2][0],P[2][1]],[P[3][0],P[3][1]]])
        P_GG = np.asarray([[P[2][2],P[2][3]],[P[3][2],P[3][3]]])

        H1 = P_FF-np.matmul(np.matmul(P_FG,np.linalg.matrix_power(P_GG,-1)),P_GF)
        H2 = np.matmul(P_FG,np.linalg.matrix_power(P_GG,-1))
        H3 = np.matmul(-np.linalg.matrix_power(P_GG,-1),P_GF)
        H4 = np.linalg.matrix_power(P_GG,-1)
        H = np.vstack((np.hstack((H1,H2)),np.hstack((H3,H4))))

        return H

    # Swap columns of a given array
    def swap_cols(self, arr, frm, to):
        arr[:,[frm, to]] = arr[:,[to, frm]]
        return arr

    # Swap rows of a given array
    def swap_rows(self, arr, frm, to):
        arr[[frm, to],:] = arr[[to, frm],:]
        return arr
        

    # Print iterations progress
    def printProgressBar (self, iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█'):
        percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
        filledLength = int(length * iteration // total)
        bar = fill * filledLength + '-' * (length - filledLength)
        print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end = '\r')
        # Print New Line on Complete
        if iteration == total: 
            print()


    # This performs a 3d interpolation to estimate effective indices
    def getPropConstants(self, bar, plot=False):
        
        T0 = 300
        dneffdT = 1.87E-04      #[/K] assuming dneff/dn=1 (well confined mode)
        if self.T_profile is None:
            self.T_profile = self.T*np.ones(self.N_seg)

        neffThermal = dneffdT*(self.T_profile-T0)

        # Import simulation results to be used for interpolation
        n1 = np.reshape(np.loadtxt("./Database/neff/neff_1.txt"),(5,5,5))
        n2 = np.reshape(np.loadtxt("./Database/neff/neff_2.txt"),(5,5,5))
        w1_w2_wvl = np.loadtxt("./Database/neff/w1_w2_lambda.txt")

        self.n1_profile = np.zeros((self.resolution, self.N_seg))
        self.n2_profile = np.zeros((self.resolution, self.N_seg))
        self.beta1_profile = np.zeros((self.resolution, self.N_seg))
        self.beta2_profile = np.zeros((self.resolution, self.N_seg))

        if bar:
            progressbar_width = self.resolution
            clc()
            print("Calculating propagation constants...")       
            self.printProgressBar(0, progressbar_width, prefix = 'Progress:', suffix = 'Complete', length = 50)

        for i in range(self.resolution): # i=lambda, j=z
            if bar: 
                clc()
                print("Calculating propagation constants...")
                self.printProgressBar(i + 1, progressbar_width, prefix = 'Progress:', suffix = 'Complete', length = 50)

            for j in range(self.N_seg):
                self.n1_profile [i,j] = neffThermal[j] + scipy.interpolate.interpn(w1_w2_wvl, n1, [self.w1_profile[j],self.w2_profile[j],self.wavelength[i]])
                self.n2_profile [i,j] = neffThermal[j] + scipy.interpolate.interpn(w1_w2_wvl, n2, [self.w1_profile[j],self.w2_profile[j],self.wavelength[i]])

            self.beta1_profile [i,:] = 2*math.pi / self.wavelength [i] * self.n1_profile [i,:]
            self.beta2_profile [i,:] = 2*math.pi / self.wavelength [i] * self.n2_profile [i,:]


        if plot:
            p1n1 = self.n1_profile[0,:]
            p2n1 = self.n1_profile[round(self.resolution/2),:]
            p3n1 = self.n1_profile[-1,:]

            p1n2 = self.n2_profile[0,:]
            p2n2 = self.n2_profile[round(self.resolution/2),:]
            p3n2 = self.n2_profile[-1,:]

            plt.figure()
            plt.plot(range(self.N_seg),p1n1,"b-",label="n1, "+str(self.wavelength[0]))
            plt.plot(range(self.N_seg),p2n1,"b--",label="n1, "+str(round(self.wavelength[round(self.resolution/2)],8)))
            plt.plot(range(self.N_seg),p3n1,"b-.",label="n1, "+str(self.wavelength[-1]))

            plt.plot(range(self.N_seg),p1n2,"r-",label="n2, "+str(self.wavelength[0]))
            plt.plot(range(self.N_seg),p2n2,"r--",label="n2, "+str(round(self.wavelength[round(self.resolution/2)],8)))
            plt.plot(range(self.N_seg),p3n2,"r-.",label="n2, "+str(self.wavelength[-1]))

            plt.legend()
            plt.xlabel("Segment number")
            plt.ylabel("Supermode Effective Indices")
            plt.show()

            clc()




    def getApodProfile(self):
        if self.apod_shape is "gaussian":
            ApoFunc=np.exp(-np.linspace(0,1,num=1000)**2)     #Function used for apodization (window function)
            mirror = False                #makes the apodization function symetrical

            l_seg = self.N*np.mean(self.period)/self.N_seg
            n_apodization=np.arange(self.N_seg)+0.5
            zaxis = (np.arange(self.N_seg))*l_seg

            if self.a == 0:
                self.apod_profile = self.kappa*np.ones(self.N_seg)

            else:
                kappa_apodG = np.exp(-self.a*((n_apodization)-0.5*self.N_seg)**2/self.N_seg**2)
                ApoFunc = kappa_apodG

                profile = (ApoFunc-min(ApoFunc))/(max(ApoFunc)-(min(ApoFunc))) # normalizes the profile

                n_profile = np.linspace(0,self.N_seg,profile.size)
                profile = np.interp(n_apodization, n_profile, profile)
                    

                kappaMin = 0 #self.kappa*profile[0]
                kappaMax = self.kappa
                kappa_apod=kappaMin+(kappaMax-kappaMin)*profile

                self.apod_profile = kappa_apod
                self.apod_profile[0] = 0
                self.apod_profile[-1] = 0

        elif self.apod_shape is "tanh":
            z = np.arange(0, self.N_seg)
            alpha, beta = 2, 3
            apod = 1/2 * (1 + np.tanh(beta*(1-2*abs(2*z/self.N_seg)**alpha)))
            apod = np.append(np.flip(apod[0:int(apod.size/2)]), apod[0:int(apod.size/2)])
            apod *= self.kappa

            self.apod_profile = apod


    # ------------------------------------------------- \
    # Section relative to chirp and chirp optimization


    # This creates a regression to estimate the reflection wavelength
    # (Only used to get parameters in optimizeParams)
    def estimate_wvl(period, dw):
    
        periods = np.arange(310e-9,330e-9,2e-9)
        lam_p = 1e-9*np.array([1526.7, 1532.7, 1538.2, 1543.6, 1549.7, 1555.8, 1561.2, 1566.7, 1572.7, 1578.2, 1583.6])
        lam = 1e-9*np.array([1560.5, 1561.7, 1563. , 1564.4, 1565.6, 1566.8, 1568., 1569.2, 1570.5, 1571.7, 1572.9])
        d_w = np.array([-1.00000000e-08, -8.00000000e-09, -6.00000000e-09, -4.00000000e-09, -2.00000000e-09, -5.29395592e-23,  2.00000000e-09,  4.00000000e-09, 6.00000000e-09,  8.00000000e-09,  1.00000000e-08])
        dlam_dp, p_0 = np.polyfit(periods, lam_p, 1)
        dlam_dw, w_0 = np.polyfit(d_w, lam, 1)
        wvl = dlam_dp*period + p_0 + dlam_dw*dw

        return wvl


    # This finds optimal period and widths combination for a targeted ref. wavelength
    def optimizeParams(self, target_wvl):
        
        error = 20e-9
        new_error = 10e-9

        # Parameters gotten from regression
        dlam_dp = 2.853181818181853
        p_0     = 6.423545454545346e-07
        dlam_dw = 0.6204545454543569

        # creating dummy device and estimating parameters through fit
        dummy = copy.copy(self)
        dummy.target_wvl = None # Most important line ever ;)
        dummy.N = 500 # Doesn't really change centre wavelength and saves time
        dummy.period = np.round((target_wvl - p_0)/dlam_dp/self.period_chirp_step)*self.period_chirp_step
        dw = np.round((target_wvl - dlam_dp*dummy.period - p_0)/dlam_dw, 9)
        dummy.w1 = dummy.w1 + dw 
        dummy.w2 = dummy.w2 + dw 

        dummy.wvl_range = [target_wvl-30e-9, target_wvl+30e-9]
        dummy.resolution = 50

        # Iterating until best combination is found
        run = True
        while run:
            error = new_error
            dummy.simulate(bar=False)
            dummy.getPerformance()
            ref = dummy.performance[0][1]*1e-9 # the ref wavelength
            new_error = ref - target_wvl

            if abs(new_error) > abs(error):
                if new_error > 0:
                    dummy.w1 = dummy.w1[0] - self.w_chirp_step
                    dummy.w2 = dummy.w2[0] - self.w_chirp_step
                elif new_error < 0:
                    dummy.w1 = dummy.w1[0] + self.w_chirp_step
                    dummy.w2 = dummy.w2[0] + self.w_chirp_step
                run = False

            elif abs(new_error) < abs(error):
                # print(new_error, dummy.w1, dummy.w2)
                if new_error > 0:
                    dummy.w1 = dummy.w1[0] - self.w_chirp_step
                    dummy.w2 = dummy.w2[0] - self.w_chirp_step
                elif new_error < 0:
                    dummy.w1 = dummy.w1[0] + self.w_chirp_step
                    dummy.w2 = dummy.w2[0] + self.w_chirp_step

            else:
                run = False

        if isinstance(dummy.w1, float):
            return dummy.period, dummy.w1, dummy.w2
        else:
            return dummy.period, dummy.w1[0], dummy.w2[0]


    # ---/ Section on chirp

    def chirpIsKnown(self):

        ID = str(self.N_seg) + "_"  \
        +str(int(self.target_wvl[0]*1e9)) \
            + "_" + str(int(self.target_wvl[-1]*1e9))

        if os.path.exists("Database/Chirp_profiles/"+ID+".txt"):
            return True

        else:
            return False


    def saveChirp(self):    

        ID = str(self.N_seg) + "_"  \
            +str(int(self.target_wvl[0]*1e9)) \
            + "_" + str(int(self.target_wvl[-1]*1e9))

        with open("Database/Chirp_profiles/"+ID+".txt", "w") as file:
            np.savetxt(file, (self.period_profile, self.w1_profile, self.w2_profile))


    def fetchChirp(self):

        ID = str(self.N_seg) + "_"  \
        +str(int(self.target_wvl[0]*1e9)) \
        + "_" + str(int(self.target_wvl[-1]*1e9))

        self.period_profile, self.w1_profile, self.w2_profile = np.loadtxt("Database/Chirp_profiles/"+ID+".txt")


    # This finds the best chirp profile to smoothly scan reflection wavelengths
    def optimizeChirp(self, start_wvl, end_wvl, bar=True):

        if self.chirpIsKnown():
            self.fetchChirp()

        else:
            ref_wvl = np.linspace(start_wvl, end_wvl, self.N_seg)
            self.period_profile = np.zeros(self.N_seg)
            self.w1_profile = np.zeros(self.N_seg)
            self.w2_profile = np.zeros(self.N_seg)

            if bar:
                progressbar_width = self.N_seg
                self.printProgressBar(0, progressbar_width, prefix = 'Progress:', suffix = 'Complete', length = 50)
                i=0

            for n in range(self.N_seg):
                self.period_profile[n], self.w1_profile[n], self.w2_profile[n] = self.optimizeParams(ref_wvl[n])

                if bar:
                    i += 1
                    clc()
                    print("Optimizing chirp profile...")
                    self.printProgressBar(i, progressbar_width, prefix = 'Progress:', suffix = 'Complete', length = 50)

            self.saveChirp()


    def getChirpProfile(self, plot=False):

        if self.target_wvl is None: # if no chirp optimization is used

            # period chirp
            if isinstance(self.period, float):
                self.period = [self.period] # convert to list
            valid_periods = np.arange(self.period[0], self.period[-1] + self.period_chirp_step/100, self.period_chirp_step)

            self.period_profile = np.repeat(valid_periods, round(self.N_seg/np.size(valid_periods)))
            while np.size(self.period_profile) < self.N_seg:
                self.period_profile = np.append(self.period_profile, valid_periods[-1])
            self.period_profile = np.round(self.period_profile, 15)
            self.period_profile = self.period_profile[:self.N_seg+1]

            # Waveguide width chirp
            if isinstance(self.w1, float):
                self.w1 = [self.w1] # convert to list
            self.w1_profile = np.linspace(self.w1[0],self.w1[-1],self.N_seg)
            self.w1_profile = np.round(self.w1_profile/self.w_chirp_step)*self.w_chirp_step
            self.w1_profile = np.round(self.w1_profile, 15)

            if isinstance(self.w2, float):
                self.w2 = [self.w2] # convert to list
            self.w2_profile = np.linspace(self.w2[0],self.w2[-1],self.N_seg)
            self.w2_profile = np.round(self.w2_profile/self.w_chirp_step)*self.w_chirp_step
            self.w2_profile = np.round(self.w2_profile, 15)

        else: # if chirp optimization is used
            self.optimizeChirp(self.target_wvl[0], self.target_wvl[-1])

        if plot:
            plt.figure()
            plt.plot(self.period_profile*1e9,"o-")
            plt.xlabel("Apodization segment")
            plt.ylabel("Period (nm)")

            plt.figure()
            plt.plot(self.w1_profile,"o-")
            plt.plot(self.w2_profile,"o-")
            plt.title("Width Chirp Profile")

            plt.show()


    def fetchParams(self, wvl):
        wavelength, period, w1, w2 = np.transpose(np.loadtxt("Database/Target_wavelengths.txt"))
        idx = (np.abs(wavelength - wvl)).argmin()

        return period[idx], w1[idx], w2[idx]


    # end section on chirp
    # --------------------------------- /


    def propagate(self, bar):
        # initiate arrays
        T = np.zeros((1, self.resolution),dtype=complex)
        R = np.zeros((1, self.resolution),dtype=complex)
        T_co = np.zeros((1, self.resolution),dtype=complex)
        R_co = np.zeros((1, self.resolution),dtype=complex)
        
        E_Thru = np.zeros((1, self.resolution),dtype=complex)
        E_Drop = np.zeros((1, self.resolution),dtype=complex)

        LeftRightTransferMatrix = np.zeros((4,4,self.resolution),dtype=complex)
        TopDownTransferMatrix = np.zeros((4,4,self.resolution),dtype=complex)
        InOutTransferMatrix = np.zeros((4,4,self.resolution),dtype=complex)

        # kappa_apod = self.getApodProfile()
        kappa_apod = self.apod_profile

        mode_kappa_a1=1
        mode_kappa_a2=0 #no initial cross coupling
        mode_kappa_b2=1
        mode_kappa_b1=0

        j = cmath.sqrt(-1)      # imaginary

        alpha_e = 100*self.alpha/10*math.log(10)

        if bar:
            progressbar_width = self.resolution
            # Initial call to print 0% progress
            self.printProgressBar(0, progressbar_width, prefix = 'Progress:', suffix = 'Complete', length = 50)
                
        # Propagation 
        # i: wavelength, related to self.resolution
        # j: profiles along grating, related to self.N_seg  
       
        for ii in range(self.resolution):
            if bar:
                clc()
                print("Propagating along grating...")
                self.printProgressBar(ii + 1, progressbar_width, prefix = 'Progress:', suffix = 'Complete', length = 50)

            l_0 = 0
            for n in range(self.N_seg):


                l_seg = self.N/self.N_seg * self.period_profile[n]          

                kappa_12 = self.apod_profile[n]
                kappa_21 = np.conj(kappa_12);
                kappa_11 = self._antiRefCoeff * self.apod_profile[n]
                kappa_22 = self._antiRefCoeff * self.apod_profile[n]

                beta_del_1 = self.beta1_profile[ii,n] - math.pi/self.period_profile[n]  - j*alpha_e/2
                beta_del_2 = self.beta2_profile[ii,n] - math.pi/self.period_profile[n]  - j*alpha_e/2

                S_1=[  [j*beta_del_1, 0, 0, 0], [0, j*beta_del_2, 0, 0],
                       [0, 0, -j*beta_del_1, 0],[0, 0, 0, -j*beta_del_2]]

                # S2 = transfert matrix
                S_2=  [[-j*beta_del_1,  0,  -j*kappa_11*np.exp(j*2*beta_del_1*l_0),  -j*kappa_12*np.exp(j*(beta_del_1+beta_del_2)*l_0)],
                       [0,  -j*beta_del_2,  -j*kappa_12*np.exp(j*(beta_del_1+beta_del_2)*l_0),  -j*kappa_22*np.exp(j*2*beta_del_2*l_0)],
                       [j*np.conj(kappa_11)*np.exp(-j*2*beta_del_1*l_0),  j*np.conj(kappa_12)*np.exp(-j*(beta_del_1+beta_del_2)*l_0),  j*beta_del_1,  0],
                       [j*np.conj(kappa_12)*np.exp(-j*(beta_del_1+beta_del_2)*l_0),  j*np.conj(kappa_22)*np.exp(-j*2*beta_del_2*l_0),  0,  j*beta_del_2]]
                # if n == 0: 

                P0 = np.matmul(scipy.linalg.expm(np.asarray(S_1)*l_seg), scipy.linalg.expm(np.asarray(S_2)*l_seg))

                if n == 0:
                    P1 = P0*1
                else:
                    P1 = np.matmul(P0,P)
                P = P1

                l_0 = l_0 + l_seg

                
            LeftRightTransferMatrix[:,:,ii] = P
            # Calculating In Out Matrix
            # Matrix Switch, flip inputs 1&2 with outputs 1&2
            H = self.switchTop(P)
            InOutTransferMatrix[:,:,ii] = H

            # Calculate Top Down Matrix
            P2 = P
            # switch the order of the inputs/outputs
            P2=np.vstack((P2[3][:], P2[1][:], P2[2][:], P2[0][:])) # switch rows
            P2=self.swap_cols(P2,1,2) # switch columns
            # Matrix Switch, flip inputs 1&2 with outputs 1&2
            P3 = self.switchTop( P2 )
            # switch the order of the inputs/outputs
            P3=np.vstack((P3[3][:], P3[0][:], P3[2][:], P3[1][:])) # switch rows
            P3=self.swap_cols(P3,2,3) # switch columns
            P3=self.swap_cols(P3,1,2) # switch columns

            TopDownTransferMatrix[:,:,ii] = P3
            T[0,ii] = H[0,0]*mode_kappa_a1+H[0,1]*mode_kappa_a2
            R[0,ii] = H[3,0]*mode_kappa_a1+H[3,1]*mode_kappa_a2

            T_co[0,ii] = H[1,0]*mode_kappa_a1+H[1,0]*mode_kappa_a2
            R_co[0,ii] = H[2,0]*mode_kappa_a1+H[2,1]*mode_kappa_a2

            E_Thru[0,ii] = mode_kappa_a1*T[0,ii]+mode_kappa_a2*T_co[0,ii]
            E_Drop[0,ii] = mode_kappa_b1*R_co[0,ii] + mode_kappa_b2*R[0,ii]

        # return results
        self.E_thru = E_Thru
        self.thru = 10*np.log10(np.abs(self.E_thru[0,:])**2)

        self.E_drop = E_Drop
        self.drop = 10*np.log10(np.abs(self.E_drop[0,:])**2)

        self.TransferMatrix = LeftRightTransferMatrix

        self.is_simulated = True
        


    def flipProfiles(self): # flips the cdc
            self.beta1_profile = np.flip(self.beta1_profile)
            self.beta2_profile = np.flip(self.beta2_profile)
            self.period_profile = np.flip(self.period_profile)



    def cascade(self):
        if self.stages > 1:
            thru1, drop1 = self.thru, self.drop
            self.flipProfiles()
            self.propagate(True)
            thru2, drop2 = self.thru, self.drop
            for _ in range(self.stages):
                if _%2 == 0:
                    drop, thru = drop2, thru2
                else:
                    drop, thru = drop1, thru1

                self.thru = self.thru + thru
                self.drop = self.drop + drop
            self.flipProfiles() # Return to original one



    # Add two CDCs to make chirped device
    def __add__(cdc1, cdc2):
        if isinstance(cdc2, ChirpedContraDC):

            cdc3 = copy.copy(cdc1)

            if cdc1.apod_profile is None:
                cdc1.getApodProfile()
            if cdc2.apod_profile is None:
                cdc2.getApodProfile()
            if cdc1.period_profile is None:
                cdc1.getChirpProfile()
            if cdc2.period_profile is None:
                cdc2.getChirpProfile()

            cdc3.apod_profile = np.append(cdc1.apod_profile, cdc2.apod_profile)
            cdc3.period_profile = np.append(cdc1.period_profile, cdc2.period_profile)
            cdc3.w1_profile = np.append(cdc1.w1_profile, cdc2.w1_profile)
            cdc3.w2_profile = np.append(cdc1.w2_profile, cdc2.w2_profile)
            cdc3.N += cdc2.N
            cdc3.N_seg += cdc2.N_seg
            cdc3.l_seg = np.append(cdc1.l_seg, cdc2.l_seg)
            cdc3.z_seg = np.append(cdc1.z_seg, cdc2.z_seg+cdc1.z_seg[-1]+(cdc2.z_seg[1]-cdc2.z_seg[0]))

            cdc1.getGdsInfo()
            cdc2.getGdsInfo()

            cdc3.gds_K = np.append(cdc1.gds_K, cdc2.gds_K)
            cdc3.gds_z = np.append(cdc1.gds_z, cdc2.gds_z)
            cdc3.gds_p = np.append(cdc1.gds_p, cdc2.gds_p)
            cdc3.gds_w1 = np.append(cdc1.gds_w1, cdc2.gds_w1)
            cdc3.gds_w2 = np.append(cdc1.gds_w2, cdc2.gds_w2)

        return cdc3


    def getGroupDelay(self):
        if self.is_simulated:
            drop_phase = np.unwrap(np.angle(self.E_drop))
            frequency = self.c/self.wavelength
            omega = 2*np.pi*frequency

            group_delay = -np.diff(drop_phase)/np.diff(omega)
            group_delay = np.squeeze(group_delay, axis=0)

            # keep same shape
            self.group_delay = np.append(group_delay, group_delay[-1])

            return self

    def simulate(self, bar=True):
        if self.apod_profile is None:
            self.getApodProfile()

        if self.w1_profile is None:
            self.getChirpProfile()

        self.getPropConstants(bar)
        self.propagate(bar)
        self.cascade()

        return self
        


    def getPerformance(self):
        if self.E_thru is not None:

            # bandwidth and centre wavelength
            dropMax = max(self.drop)
            drop3dB = self.wavelength[self.drop > dropMax - 3]
            ref_wvl = (drop3dB[-1] + drop3dB[0]) /2
            # TODO: something to discard sidelobes from 3-dB bandwidth
            bandwidth = drop3dB[-1] - drop3dB[0]

            # Top flatness assessment
            dropBand = self.drop[self.drop > dropMax - 3]
            avg = np.mean(dropBand)
            std = np.std(dropBand)

            self.performance = {
                            "Ref. wvl" : [np.round(ref_wvl*1e9, 2), "nm"],
                            "BW"       : [np.round(bandwidth*1e9, 2), "nm"],
                            "Max ref." : [np.round(dropMax,2), "dB"],
                            "Avg ref." : [np.round(avg,2), "dB"],
                            "Std dev." : [np.round(std,2), "dB"] }


    # Display Plots and figures of merit 
    def displayResults(self, advanced=False, tag_url=False):

        self.getPerformance()

        fig = plt.figure(figsize=(9,6))

        plt.style.use('ggplot')
        plt.rcParams['axes.prop_cycle'] = cycler('color', ['blue', 'red', 'black', 'green', 'brown', 'orangered', 'purple'])

        profile_ticks = np.round(np.linspace(0, self.N_seg, 4))
        text_color = np.asarray([0,0,0]) + .25

        grid = plt.GridSpec(6,3)

        plt.subplot(grid[0:2,0])
        plt.title("Grating Profiles", color=text_color)
        plt.plot(range(self.N_seg), self._apod_profile, ".-")
        plt.xticks(profile_ticks, size=0)
        plt.yticks(color=text_color)
        plt.ylabel("Coupling (/mm)", color=text_color)
        plt.grid(b=True, color='w', linestyle='-', linewidth=1.5)
        plt.tick_params(axis=u'both', which=u'both',length=0)

        plt.subplot(grid[2:4,0])
        plt.plot(range(self.N_seg), self._period_profile, ".-")
        plt.xticks(profile_ticks, size=0)
        plt.yticks(color=text_color)
        plt.ylabel("Pitch (nm)", color=text_color)
        plt.grid(b=True, color='w', linestyle='-', linewidth=1.5)
        plt.tick_params(axis=u'both', which=u'both',length=0)

        plt.subplot(grid[4,0])
        plt.plot(range(self.N_seg), self._w2_profile, ".-", label="wg 2")
        plt.ylabel("w2 (nm)", color=text_color)
        plt.xticks(profile_ticks, size=0, color=text_color)
        plt.yticks(color=text_color)
        plt.grid(b=True, color='w', linestyle='-', linewidth=1.5)
        plt.tick_params(axis=u'both', which=u'both',length=0)

        plt.subplot(grid[5,0])
        plt.plot(range(self.N_seg), self._w1_profile, ".-", label="wg 1")
        plt.xlabel("Segment", color=text_color)
        plt.ylabel("w1 (nm)", color=text_color)
        plt.xticks(profile_ticks, color=text_color)
        plt.yticks(color = text_color)
        plt.grid(b=True, color='w', linestyle='-', linewidth=1.5)
        plt.tick_params(axis=u'both', which=u'both',length=0)

        plt.subplot(grid[0:2,1])
        plt.title("Specifications", color=text_color)
        numElems = 6
        plt.axis([0,1,-numElems+1,1])
        plt.text(0.5,-0,"N : " + str(self.N),fontsize=11,ha="center",va="bottom", color=text_color)
        plt.text(0.5,-1,"N_seg : " + str(self.N_seg),fontsize=11,ha="center",va="bottom", color=text_color)
        plt.text(0.5,-2,"a : " + str(self.a),fontsize=11,ha="center",va="bottom", color=text_color)
        plt.text(0.5,-3,"p: " + str(self._period)+" nm",fontsize=11,ha="center",va="bottom", color=text_color)
        plt.text(0.5,-4,"w1 : " + str(self._w1)+" nm",fontsize=11,ha="center",va="bottom", color=text_color)
        plt.text(0.5,-5,"w2 : " + str(self._w2)+" nm",fontsize=11,ha="center",va="bottom", color=text_color)
        plt.xticks([])
        plt.yticks([])
        plt.box(False)


        plt.subplot(grid[0:2,2])
        plt.title("Performance", color=text_color)
        numElems = len(self.performance)
        plt.axis([0,1,-numElems+1,1])
        for i, item  in zip(range(len(self.performance)), self.performance):
            plt.text(0.5,-i, item +" : ", fontsize=11, ha="right", va="bottom", color=text_color)
            plt.text(0.5,-i, str(self.performance[item][0])+" "+self.performance[item][1], fontsize=11, ha="left", va="bottom", color=text_color)
        plt.xticks([])
        plt.yticks([])
        plt.box(False)

        
        plt.subplot(grid[2:,1:])
        plt.plot(self.wavelength*1e9, self.thru, label="Thru port")
        plt.plot(self.wavelength*1e9, self.drop, label="Drop port")
        plt.legend(loc="best", frameon=False)
        plt.xlabel("Wavelength (nm)", color=text_color)
        plt.ylabel("Response (dB)", color=text_color)
        plt.tick_params(axis='y', which='both', labelleft=False, labelright=True, \
                        direction="in", right=True, color=text_color)
        plt.yticks(color=text_color)
        plt.xticks(color=text_color)
        # plt.tick_params(axis='x', top=True)
        plt.grid(b=True, color='w', linestyle='-', linewidth=1.5)
        plt.tick_params(axis=u'both', which=u'both',length=0)

        if tag_url:
            url = "https://github.com/JonathanCauchon/Contra-DC"
            plt.text(self._wavelength.min(), min(self.drop.min(), self.thru.min()), url, va="top", color="grey", size=6)

        plt.show()

    def plot_format(self):
        plt.style.use('ggplot')
        plt.rcParams['axes.prop_cycle'] = cycler('color', ['blue', 'red', 'black', 'green', 'brown', 'orangered', 'purple'])
        plt.grid(b=True, color='w', linestyle='-', linewidth=1.5)
        plt.tick_params(axis=u'both', which=u'both',length=0)
        plt.legend(frameon=False)

    # export design for easy GDS implementation
    def getGdsInfo(self, corrugations=[38e-9, 32e-9], gap=100e-9, plot=False):
        if self.apod_profile is None:
            self.getApodProfile()
        N_per_seg = int(self.N/self.N_seg)
        kappa = np.repeat(self.apod_profile, 2*N_per_seg)
        corru1 = kappa/self.kappa * corrugations[0]
        corru2 = kappa/self.kappa * corrugations[-1]

        self.getChirpProfile()

        w1 = np.repeat(self.w1_profile, 2*N_per_seg)
        w2 = np.repeat(self.w2_profile, 2*N_per_seg)
        w = np.hstack((w1, w2))
        

        self.getChirpProfile()

        # print(self.period_profile.shape)
        half_p = np.repeat(self.period_profile/2, 2*N_per_seg)
        # gds_w1 = self.w1*np.ones(2*self.N)
        # gds_w2 = self.w2*np.ones(2*self.N)

        z = np.cumsum(half_p)
        z -= z[0]
        # z = np.hstack((z, z))
        half_p = np.hstack((half_p, half_p))

        x1 = corru1/2*np.ones(2*self.N)
        x1[1::2] *= -1

        x2 = -w1/2 - gap - w2/2 + corru2/2*np.ones(2*self.N)
        x2[1::2] -= 2*corru2[1::2]/2
        x2 *= -1 # symmetric grating

        info_pos = np.hstack((np.vstack((z, x1)), np.vstack((z, x2)))).transpose()
        
        info_pos *= 1e6
        half_p *= 1e6

        if plot:
            plt.plot(info_pos[0:2*self.N,0], info_pos[0:2*self.N,1])
            plt.plot(info_pos[2*self.N:,0], info_pos[2*self.N:,1])
            plt.title("Rectangle centers")

            plt.figure()
            plt.plot(info_pos[:,0], w*1e6, ".")
            plt.title("WG Widths")

            plt.figure()
            plt.plot(info_pos[:,0], half_p, ".")
            plt.title("Half Period Profile")

            plt.show()

        self.gds_pos = info_pos
        self.gds_half_p = half_p
        self.gds_w = w*1e6

        return self.gds_pos, self.gds_half_p

    def exportGdsInfo(self, fileName="auto", plot=False): 
        self.getGdsInfo(plot=plot)
        data = np.vstack((self.gds_pos[:,0], self.gds_pos[:,1], self.gds_w, self.gds_half_p)).transpose()
        data = np.round(data, 3)

        if fileName == "auto":
            fileName = str(self.apod_shape)+"_N_"+str(self.N)+"_p_"+str(round(self.period_profile[0]*1e9))+"_"+str(round(self.period_profile[-1]*1e9))+"_Nseg_"+str(self.N_seg)
        
        np.savetxt("Designs/"+fileName+".txt", data, fmt="%4.3f")




def matrix_exp(A, use_exact_onenorm):
    k = 5
    import scipy.sparse.linalg.matfuncs as mf
    return mf._expm(k*A, use_exact_onenorm)**(1/k)

def mexp_brute(A, order=2):
    """ https://en.wikipedia.org/wiki/Matrix_exponential#Properties """

    import math
    for k in range(order + 1):
        A += 1/math.factorial(k) * A**k

    return A




