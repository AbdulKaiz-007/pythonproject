
import pyttsx3
import speech_recognition as sr

def take_commands():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print('Listening')
        r.pause_threshold = 0.7
        audio = r.listen(source)
        try:
            print("Recognizing")
            Query = r.recognize_google(audio)
            print("the query is printed='", Query, "'")
        except Exception as e:
            print(e)
            print("Say that again sir")
            # returning none if there are errors
            return "None"
    # returning audio as text
    return Query
    
# creating Speak() function to giving Speaking power
# to our voice assistant 
def Speak(audio):
    # initializing pyttsx3 module
    engine = pyttsx3.init()
    # anything we pass inside engine.say(),
    # will be spoken by our voice assistant
    engine.say(audio)
    engine.runAndWait()


# Driver Code
if __name__ == '__main__':
    # using while loop to communicate infinitely
    while True:
        command = take_commands()
        if "hello Jarvis" in command:
            Speak("Hello sir")
        if "how are you" in command:
            Speak("I AM GOOD SIR")
        if "how was your day" in command:
            Speak("it was good sir")
        if "Bruce Lee" in command:
            Speak("Be like Water My friend by Bruce Lee")
        if "hello sir" in command:
            Speak("Hello Mr.Boopalan")       
        if "close Jarvis" in command:
            Speak("shutting down jarvis")
            break