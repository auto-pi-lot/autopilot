/*
Module that produces pulse trains.


NOTES:
- If train 2 starts after train 1, the pulses of train 2 will be in sync with train 1 (not train 2 onset).

*/

//#define HARDWARE_TEST


#define BOARD_LED_PIN 13

// PINS
int TRIGGER_UP_PIN = 53;
int TRIGGER_DOWN_PIN = 52;
int OUTPUT_UP_PIN = 23;
int OUTPUT_DOWN_PIN = 22;

int TRIGGER_UP_PIN2 = 51;
int TRIGGER_DOWN_PIN2 = 50;
int OUTPUT_UP_PIN2 = 25;
int OUTPUT_DOWN_PIN2 = 24;


// Variables
int state = 0;
int onTime = 10;  // In millisec if using delay(), in microsec if using delayMicrosec()
int offTime = 200; // In millisec if using delay(), in microsec if using delayMicrosec()
boolean trainOn = false;
boolean trainOn2 = false;

void setup() {
    pinMode(BOARD_LED_PIN, OUTPUT);
    digitalWrite(BOARD_LED_PIN, LOW);    // sets the LED off
    
    pinMode(TRIGGER_UP_PIN, INPUT); // INPUT_PULLDOWN
    pinMode(TRIGGER_DOWN_PIN, INPUT_PULLUP);
    pinMode(OUTPUT_UP_PIN, OUTPUT);
    pinMode(OUTPUT_DOWN_PIN, OUTPUT);
    digitalWrite(OUTPUT_UP_PIN, LOW);
    digitalWrite(OUTPUT_DOWN_PIN, HIGH);

    pinMode(TRIGGER_UP_PIN2, INPUT); // INPUT_PULLDOWN
    pinMode(TRIGGER_DOWN_PIN2, INPUT_PULLUP);
    pinMode(OUTPUT_UP_PIN2, OUTPUT);
    pinMode(OUTPUT_DOWN_PIN2, OUTPUT);
    digitalWrite(OUTPUT_UP_PIN2, LOW);
    digitalWrite(OUTPUT_DOWN_PIN2, HIGH);
}


void loop() {
    trainOn = (digitalRead(TRIGGER_UP_PIN) || !digitalRead(TRIGGER_DOWN_PIN));
    trainOn2 = (digitalRead(TRIGGER_UP_PIN2) || !digitalRead(TRIGGER_DOWN_PIN2));
    if (trainOn || trainOn2) {
        if (state) {
            if (trainOn) {
                digitalWrite(BOARD_LED_PIN, LOW);
                digitalWrite(OUTPUT_UP_PIN, LOW);
                digitalWrite(OUTPUT_DOWN_PIN, HIGH);
            }
            if (trainOn2) {
                digitalWrite(OUTPUT_UP_PIN2, LOW);
                digitalWrite(OUTPUT_DOWN_PIN2, HIGH);
            }
            //delayMicroseconds(offTime);
            delay(offTime);
            state = 0;
        }
        else {        
            if (trainOn) {
                digitalWrite(BOARD_LED_PIN, HIGH);
                digitalWrite(OUTPUT_UP_PIN, HIGH);
                digitalWrite(OUTPUT_DOWN_PIN, LOW);
            }
            if (trainOn2) {
                digitalWrite(OUTPUT_UP_PIN2, HIGH);
                digitalWrite(OUTPUT_DOWN_PIN2, LOW);
            }
            //delayMicroseconds(onTime);
            delay(onTime);
            state = 1;
        }
    }
    else {
        if (!trainOn) {
            digitalWrite(BOARD_LED_PIN, LOW);
            digitalWrite(OUTPUT_UP_PIN, LOW);
            digitalWrite(OUTPUT_DOWN_PIN, HIGH);
        }
        if (!trainOn2) {
            digitalWrite(OUTPUT_UP_PIN2, LOW);
            digitalWrite(OUTPUT_DOWN_PIN2, HIGH);
        }
        if (!trainOn && !trainOn2) {
            state = 0;
        }
    }    
}

