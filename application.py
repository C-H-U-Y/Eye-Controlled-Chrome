from contextlib import redirect_stderr
import wave, struct
import numpy as np
import matplotlib.pyplot as plt
from drawnow import *
import time
import matplotlib.patches as mpatches
import statistics
from errno import ENETRESET
from statistics import mode
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
import math
import sys, select
import time
import numpy as np
import multiprocessing
import serial
import numpy as np
import matplotlib.pyplot as plt
from drawnow import *
from scipy.io import wavfile
from scipy import signal
from sklearn.linear_model import LinearRegression
import matplotlib.patches as mpatches
import statistics


def process_byte_data(data_raw):
    """
    Converts the weird data from SpikerBox to list of amplitude measurements.

    Data from SpikerBox uses two bytes for a single unit of data. Hence returned array with be ~1/2 the size of the
    passed array.
    """
    # data_raw = np.array(b_data)
    # print(len())
    data_processed = np.zeros(0)

    i = 0
    while i < len(data_raw) - 1:

        if data_raw[i] > 127:
            # Found beginning of frame. Extract one sample from two bytes.
            int_processed = (np.bitwise_and(data_raw[i], 127)) * 128

            # To center the data around 0 in our plot and for threshold accuracy, lets transform the data down 512
            # TODO: Configure thresholds and this transformation with a setup phase? 
            int_processed = int_processed - 512

            i += 1
            int_processed += data_raw[i]

            # Allocates, fills and returns new array. Likely inefficient.
            data_processed = np.append(data_processed, int_processed)

        i += 1

    return data_processed


# Left right detection
# Removed redundant parameter "window size"
def LR_detection(seq):
    # print(len(seq))
    seq = seq.tolist()
    # print(statistics.variance(seq))

    differences = []
    
    i = 0
    while(i+100 < len(seq)):
        differences.append(abs(seq[i+99] - statistics.mean(seq[i:i+98])))
        i += 100
    
    print("dif: " + statistics.mean(differences))
    # print("cov: " + findcov(seq))
    blink_dif_threshold = 10

    if(statistics.mean(differences) > blink_dif_threshold):
        return("blink")

    maxval = seq.index(max(seq))
    minval = seq.index(min(seq))

    if minval < maxval:
        return("left")
    else:
        return("right")


def stream_input(conn, c_port):
    # Draw live data
    plt.ion()   

    # Baudrate and sample frequency is set by SpikerBox Arduino software
    b_rate = 230400
    Fs = 10000

    # Determines the size of the array that data is being filled into.
    # SpikerBox does 10000 samples/sec, but each sample is 2 bytes long,
    # hence in a usual streaming capacity, 20000 buffer size  = 1 sec.
    # Note that buffer size can be smaller than this to make window
    # sampling smaller
    inputBufferSize = int(Fs)

    # For archie's laptop COM3 is the good port
    # c_port = "COM3"

    #-------------------
    # PORT NOTE
    #-------------------
    # You can't connect to the port in python script if the spiker box recorder is running in the background
    # also connected to that port. Close the spiker box session before running this code

    # Try and open the port
    try:
        ser = serial.Serial(port=c_port, baudrate=b_rate)
        ser.set_buffer_size(rx_size= inputBufferSize)
        ser.timeout = inputBufferSize/Fs
    except serial.serialutil.SerialException:
        raise Exception(f'Could not open port {c_port}.\nFind port from:\nDevice Manager > Ports (COM & LPT) [Windows]')

    # Define plot function needed for drawnow
    def makeFig():
        plt.plot(data_plot, 'g-')
        plt.ylim([-500, 500])

    # Convert the 2 bytes of data send from SpikerBox to an array of numbers
    def process_byte_data(b_data):
        """
        Converts the weird data from SpikerBox to list of amplitude measurements.

        Data from SpikerBox uses two bytes for a single unit of data. Hence returned array with be ~1/2 the size of the
        passed array.
        """
        data_raw = np.array(b_data)
        data_processed = np.zeros(0)

        i = 0
        while i < len(data_raw) - 1:

            if data_raw[i] > 127:
                # Found beginning of frame. Extract one sample from two bytes.
                int_processed = (np.bitwise_and(data_raw[i], 127)) * 128

                # To center the data around 0 in our plot and for threshold accuracy, lets transform the data down 512
                # TODO: Configure thresholds and this transformation with a setup phase? 
                int_processed = int_processed - 512

                i += 1
                int_processed += data_raw[i]

                # Allocates, fills and returns new array. Likely inefficient.
                data_processed = np.append(data_processed, int_processed)

            i += 1

        return data_processed



    # Left right detection
    # Removed redundant parameter "window size"
    def LR_detection(seq):
        # print(len(seq))
        seq = seq.tolist()
        # print(statistics.variance(seq))

        differences = []
        
        i = 0
        while(i+100 < len(seq)):
            differences.append(abs(seq[i+99] - statistics.mean(seq[i:i+98])))
            i += 100
        

        # conn.send("NOT INPUT: " + str(statistics.mean(differences)))

        blink_dif_threshold = 6
        # print(statistics.mean(differences))
        if(statistics.mean(differences) > blink_dif_threshold):
            return("blink")

        maxval = seq.index(max(seq))
        minval = seq.index(min(seq))

        if minval < maxval:
            return("left")
        else:
            return("right")


    # New function
    # Takes in the normal .WAV file parameters and decides if there is an event.
    # This function is supposed to be a very quick event detection, it is handed 2 
    # seconds of data ever 0.5 seconds and should detect any event in the last 0.5
    # seconds of data.
    #   0s                1s                2s                3s                4s                5s   
    #   |--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
    #   
    #   WHAT THE FUNCTION SEES
    #   | ---- 2 seconds with no event ---- |                                       (Started at 0 seconds)
    #            | ---- 2 seconds with no event ---- |                              (started at 0.5 seconds)
    #                     | 2 seconds with event starting in  |                     (started at 1 seconds)
    #                     |     the last 0.5 seconds          |             
    # 
    #   WHAT IS ACTUALL HAPPENING
    #   ------------------------------------------------|     1.7 second event    | (event goes from 2.6 seconds until 4.1 seconds)      
    #
    # Here we can see the function taking in 2 seconds of data every 0.5 seconds. It will detect if there is an event in the final
    # 0.5 seconds of that 2 seconds and return "SIGNAL" 
    def detect_event(waveSeq):
        """
        Take in 2 seconds, and return "SIGNAL" if theres an eye movement. 
        The goal is to be sensitive enough that signals are deteced in the latest 0.5 seconds of the given signal
        """
        # Threshold for a signal, this might need calibration each time. If the max value in the 2 seconds is higher
        # than this value than there is probably the start of a signal
        threshold = 200

        # TODO: We may need some filter to check make sure that this isn't just a missread value (sometime there are random peaks) 
        # that might surpass this threshold

        if(max(waveSeq) > threshold or min(waveSeq) < -threshold):
            return "SIGNAL"


    # Create a lowpass filter
    b, a = signal.butter(8, 0.01, 'lowpass') #set filters 8 as filter order 
    # 0.2 is WN The critical frequency or frequencies need adjust!

    #==================================
    # STREAMING CODE
    #==================================

    total_time = 10000.0; # time in seconds [[1 s = 20000 buffer size]]
    max_time = 5; # time plotted in window [s]
    N_loops = (2*Fs/inputBufferSize)*total_time

    T_acquire = inputBufferSize/(2*Fs)    # length of time that data is acquired for 
    N_max_loops = max_time/T_acquire    # total number of loops to cover desire time window


    #--------------------------------
    # Variable setup for live event classification
    #-------------------------------

    # Mark - he tells us the 'k' (how many 0.5 seconds) value when a signal is first detected. 
    # Starting value of negative so it can be set to some non zero positive value when streaming starts
    mark = -400

    # We are not currently 'in a signal'. The 'in signal' state means that we have detected the start
    # of a signal with detect_event() function and now we're waiting for the rest of the signal to happen
    # so we can classify it
    not_in_signal = True

    # The data cache, this stores the most recent 2 seconds, every time the loop is run, 0.5 seconds is
    # is added to the cache and an old 0.5 seconds is removed
    data_cache = []
    # data cache is an array of arrays where each array in data chache is a 0.5 second block of WAV file data


    for k in range(0,int(N_loops)):
        
        # Read data from SpikerBox into a buffer of size input_buffer_size.
        byte_data = ser.read(inputBufferSize)

        # Cast to list of ints.
        byte_data = [int(byte_data[i]) for i in range(len(byte_data))]

        # Process with function defined above
        data_temp = process_byte_data(byte_data)

        # Filter the small amplitudes (between -100 and 100)
        # amplitude_filter(data_temp, -50, 50)

        # Fourier Filter the data
        # data_temp = signal.filtfilt(b, a, data_temp)

        # Add to the data cache
        data_cache.append(data_temp)
        
        if k <= N_max_loops:

            # If we're at the first data entry, we cannot append
            if k==0:
                data_plot = data_temp
            else:
                #data_plot = np.append(data_temp, data_plot)
                data_plot = np.append(data_temp, data_plot) # Plot from left to right by appending on the end
        else:
            # We have reached the end of the specified number of loops
            data_plot = np.roll(data_plot, len(data_temp))
            data_plot[0:len(data_temp)] = data_temp

        # If there is now 5 lots of 0.5 seconds in our data cache, remove one so there is always 4
        if(len(data_cache) == 5):
            data_cache.pop(0)
        
        combined = np.concatenate(data_cache)

        # If we aren't currently in a signal, check if there is a signal
        if(not_in_signal):
            if(detect_event(combined) == "SIGNAL"):
                # print("start signal")
                pause = True
                
                # we have a signal detected. lets mark the current k value and update our boolean
                mark = k
                not_in_signal = False
        
        # We are now one second after the signal has been detected. that means the whole
        # signal should be in our data cache. Let's analyse the signal.  
        if(k == mark + 2):
            # print("end signal")
            conn.send(LR_detection(combined))
            # print("prediction: " + LR_detection(combined))
            data_cache = []
            not_in_signal = True

        drawnow(makeFig)
        if(k == 0):
            plt.pause(10)
            time.sleep(10)
    
        plt.pause(.000001)

    # Close the serial port
    if ser.read():
        ser.flushInput()
        ser.flushOutput()
        ser.close()


    exit()


def run_application(conn):
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

    #By deafult we'll open to google and be inputting text for search bar
    driver.get("https://www.google.com")
    search = True

    def morse(blinks):
        error = 'ERROR: Morse Not Recognised'
    # morse of length 1
        if len(blinks)==1:
            if blinks[0]=='left':
                out = 'e'
            elif blinks[0]=='right':
                out = 't'
    # morse of length 2
        elif len(blinks)==2:
            if blinks[0]=='left':
                if blinks[1]=='left':
                    out = 'i'
                elif blinks[1]=='right':
                    out = 'a'
            elif blinks[0]=='right':
                if blinks[1]=='left':
                    out = 'n'
                elif blinks[1]=='right':
                    out = 'm'
    # morse of length 3
        elif len(blinks)==3:
            if blinks[0]=='left':
                if blinks[1]=='left':
                    if blinks[2]=='left':
                        out = 's'
                    elif blinks[2]=='right':
                        out = 'u'
                elif blinks[1]=='right':
                    if blinks[2]=='left':
                        out = 'r'
                    elif blinks[2]=='right':
                        out = 'w'
            elif blinks[0]=='right':
                if blinks[1]=='left':
                    if blinks[2]=='left':
                        out = 'd'
                    elif blinks[2]=='right':
                        out = 'k'
                elif blinks[1]=='right':
                    if blinks[2]=='left':
                        out = 'g'
                    elif blinks[2]=='right':
                        out = 'o'
    # morse of length 4
        elif len(blinks)==4:
            if blinks[0]=='left':
                if blinks[1]=='left':
                    if blinks[2]=='left':
                        if blinks[3]=='left':
                            out = 'h'
                        elif blinks[3]=='right':
                            out = 'v'
                    elif blinks[2]=='right':
                        if blinks[3]=='left':
                            out = 'f'
                        elif blinks[3]=='right':
                            out = error
                elif blinks[1]=='right':
                    if blinks[2]=='left':
                        if blinks[3]=='left':
                            out = 'l'
                        elif blinks[3]=='right':
                            out = error
                    elif blinks[2]=='right':
                        if blinks[3]=='left':
                            out = 'p'
                        elif blinks[3]=='right':
                            out = 'j'
            elif blinks[0]=='right':
                if blinks[1]=='left':
                    if blinks[2]=='left':
                        if blinks[3]=='left':
                            out = 'b'
                        elif blinks[3]=='right':
                            out = 'x'
                    elif blinks[2]=='right':
                        if blinks[3]=='left':
                            out = 'c'
                        elif blinks[3]=='right':
                            out = 'y'
                elif blinks[1]=='right':
                    if blinks[2]=='left':
                        if blinks[3]=='left':
                            out = 'z'
                        elif blinks[3]=='right':
                            out = 'q'
                    elif blinks[2]=='right':
                        if blinks[3]=='left':
                            out = error
                        elif blinks[3]=='right':
                            out = error
    # morse length 5 - numbers
        elif len(blinks)==5:
            dot_count = sum(np.array(blinks)=='left')
        #range 1-5
            if blinks[0]=='left':
                num15 = [1,2,3,4,5]
                out = num15[dot_count-1]
        #range 6-0
            elif blinks[0]=='right':
                num60 = [0,9,8,7,6]
                out = num60[dot_count]
    # morse length 6 - punctuation
        elif len(blinks)==6:
            if blinks[0]=='left':
                if blinks[1]=='left':
                    out = '?'
                elif blinks[0]=='right':
                    out = '.'
            elif blinks[0]=='right':
                if blinks[1]=='left':
                    out = '!'
                elif blinks[1]=='right':
                    out = ','
        else:
            out = error
        return out


    #Our morse code translator function
    def MCR(array):
        print("You have sent the following data to the Morse Code Translator: ")
        print(array)
        return "Since this function isn't built yet, please tell me what the letter is supposed to be:"

    def textInputMode(driver, element):
        print("\n========================")
        print("Entering text input mode")
        print("========================\n")


        #blink left = nav mode
        #blink blink = submit
        #blink right = space bar

        previous_blink = False
        
        total_input = ""
        
        while(True): 
            brain_input = conn.recv()

            print("INPUT RECIEVED: " + brain_input)
            
            if(brain_input == "blink"):
                if(previous_blink):
                    previous_blink = False

                    next_input = conn.recv()
                    print("INPUT RECIEVED: " + next_input)

                    if(next_input == "left"):   
                        print("\n========================")
                        print("Exiting text input mode")
                        print("========================\n")
                        navigationMode(driver)

                    if(next_input == "right"):
                        element.send_keys(" ")

                    if(next_input == "blink"):
                        ActionChains(driver).send_keys(Keys.ENTER).perform()
                        print("\n========================")
                        print("Exiting text input mode")
                        print("========================\n")
                        navigationMode(driver)

                else:
                    previous_blink = True
                    if(total_input != ""):
                        array_input = (total_input.split())
                        """
                        #Call MCR
                        letter_val = MCR(array_input)        
                        #send to selenium
                        letter_val = input(letter_val)
                        """

                        letter_val = morse(array_input)

                        element.send_keys(letter_val)
                        total_input = ""
                
            else:
                previous_blink = False
                total_input = total_input + " " + brain_input

    def navigationMode(driver):
        print("\n========================")
        print("Entering navigation mode")
        print("========================\n")

        while(True):
            brain_input = conn.recv()
            
            print("INPUT RECIEVED: " + brain_input)

            if(brain_input == "left"):
                brain_input = "right"
            
            elif(brain_input == "right"):
                brain_input = "left"
            
            if(brain_input == "left"):
                ActionChains(driver).send_keys(Keys.TAB).perform()

            elif(brain_input == "right"):
                ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.TAB).key_up(Keys.SHIFT).perform()

            elif(brain_input == "blink"):
                #Check if they want to enter or if they want to switch to text input
                brain_input = conn.recv()

                print("INPUT RECIEVED: " + brain_input)

                if(brain_input == "blink"):
                    #double click, enter page
                    ActionChains(driver).send_keys(Keys.ENTER).perform()
                
                else:
                    #Enter text input mode
                    textInputMode(driver, driver.switch_to.active_element)

    try:
        driver.get("https://www.google.com")
        driver.set_window_size(1250, 480)

        time.sleep(3)

        #Search first
        if(search):
            print("\n\n\n===============================================")
            print("WELCOME TO THE AMEFY EYE CONTROLLED WEB BROWSER")
            print("======= please enter your google search =======\n")

            searchbar = driver.find_elements(By.NAME, 'q')[0]
            searchReturn = textInputMode(driver, searchbar)

        # #pretend search was done here (will wait for input then move on), for debug
        # brain_input = input("")    

        try:
            driver.quit()
        except:
            print("excepted")

    #aS^UI&DGYUADBHSAVTD&Ia6&SDASD&S&%76d
    #sellyniam@gmail.com
    #sellenium
    except:
        
        try:
            driver.quit()
        except:
            print("Exiting")


def data_streaming_process(conn, c_port):
    time.sleep(10)
    stream_input(conn, c_port)

    # conn.send("hi")
    # return
  
def application_running_process(conn):
    run_application(conn)

def run():
    c_port = input('Which port?\n')

    conn1, conn2 = multiprocessing.Pipe()
    process_1 = multiprocessing.Process(target=data_streaming_process, args=(conn1,c_port,))
    process_2 = multiprocessing.Process(target=application_running_process, args=(conn2,))
    process_1.start()
    process_2.start()
    process_1.join()
    process_2.join()


if __name__ == "__main__":
    run()