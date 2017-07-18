/*
State machine for arduino DUE


NOTES:
- During development I set inputs as INPUT_PULLUP
- During development I inverted the inputs

XXFIXME:
- There must be a better way to transfer large datasets (e.g., statematrix) than
  using while(!Serial.available()) before every byte.

*/

//#define HARDWARE_TEST

#define OK                    0xaa
#define RESET                 0x01  // OBSOLETE
#define CONNECT               0x02
#define TEST_CONNECTION       0x03
#define SET_SIZES             0x04
#define GET_SERVER_VERSION    0x05
#define GET_TIME              0x06
#define GET_INPUTS            0x0e
#define FORCE_OUTPUT          0x0f
#define SET_STATE_MATRIX      0x10
#define RUN                   0x11
#define STOP                  0x12
#define GET_EVENTS            0x13
#define REPORT_STATE_MATRIX   0x14
#define GET_CURRENT_STATE     0x15
#define FORCE_STATE           0x16
#define SET_STATE_TIMERS      0x17
#define REPORT_STATE_TIMERS   0x18
#define SET_STATE_OUTPUTS     0x19
#define SET_EXTRA_TIMERS      0x1a
#define SET_EXTRA_TRIGGERS    0x1b
#define REPORT_EXTRA_TIMERS   0x1c
#define SET_SERIAL_OUTPUTS    0x1d
#define REPORT_SERIAL_OUTPUTS 0x1e

#define TEST                 0xee
#define ERROR                0xff

#define VERSION        "0.2"

#define MAXNEVENTS 512
#define MAXNSTATES 256
#define MAXNEXTRATIMERS 16
#define MAXNINPUTS  8
#define MAXNOUTPUTS  16
#define MAXNACTIONS 2*MAXNINPUTS + 1 + MAXNEXTRATIMERS

// NOTE: inputPins needs to be consistent with MAXNINPUTS
unsigned int inputPins[] = {53,52,51,50, 49,48,47,46};
unsigned int inputValues[MAXNINPUTS];
unsigned int previousValue;

#define ledPin 13
// NOTE: outputPins needs to be consistent with MAXNOUTPUTS
unsigned int outputPins[] = {22,23,24,25, 26,27,28,29, 30,31,32,33, 34,35,36,37};
//unsigned int outputValues[MAXNOUTPUTS]; // UNUSED
unsigned int serialOutputs[MAXNSTATES]; // One byte serial output per state
unsigned int indpin;
unsigned long currentTime = 0;
unsigned long lastTime = 0;
unsigned int bytecounter = 0;
unsigned char serialByte;


// NOTE: volatile qualifier is needed for variables changed within interrupt calls
unsigned long eventTime = 0;
volatile boolean runningState = false;
volatile unsigned long eventsTime[MAXNEVENTS];
volatile int eventsCode[MAXNEVENTS];
volatile int nEvents = 0;
volatile int eventsToProcess = 0;
unsigned char currentState = 0;
unsigned char previousState = 0;
unsigned char nextState[MAXNEVENTS];

unsigned char nStates; // Number of states
unsigned char nInputs; // Number of inputs
unsigned char nExtraTimers; // Number of extra timers
unsigned char nActions; // Number of actions (rise/fall for each input, plus timers)
unsigned char nOutputs; // Number of outputs
boolean sizesSetFlag; // Set when sizes of inputs, outputs, etc, have been defined

unsigned char stateMatrix[MAXNSTATES][MAXNACTIONS];
unsigned long stateTimers[MAXNSTATES];
unsigned char stateOutputs[MAXNSTATES][MAXNOUTPUTS];
unsigned long extraTimers[MAXNEXTRATIMERS];
unsigned char triggerStateEachExtraTimer[MAXNEXTRATIMERS];

unsigned int inds; // To index states
unsigned int inde; // To index events
unsigned int indi; // To index inptus
unsigned int indo; // To index outputs
unsigned int indt; // To index extra timers

unsigned long stateTimerValue = 0;
unsigned long extraTimersValues[MAXNEXTRATIMERS];
boolean activeExtraTimers[MAXNEXTRATIMERS];


// For debugging purposes //
void blink(int ntimes) {
  int indt;
  for (indt=0; indt<ntimes; indt++) {
    delay(100);
    digitalWrite(ledPin, HIGH);
    delay(100);
    digitalWrite(ledPin, LOW);
  }
}

void establishConnection() {
  while(1) {
    if ((Serial.available()>0) && (Serial.read()==CONNECT)) break;
    else delay(300);
  }
  Serial.write(OK);
}

void initialize() {
  // -- Initialize pins --
  for (indi=0; indi < MAXNINPUTS; indi++) {
#ifdef HARDWARE_TEST
    pinMode(inputPins[indi],INPUT_PULLUP); // Is the pull-up necessary? is it right?
#else
    pinMode(inputPins[indi],INPUT);
#endif
  }
  for (indo=0; indo < MAXNOUTPUTS; indo++) {
    pinMode(outputPins[indo],OUTPUT);
    //outputValues[indo] = LOW;  // UNUSED
    digitalWrite(outputPins[indo],LOW);
  }

  // -- Set all serial outputs to no-output --
  for (inds=0; inds<MAXNSTATES; inds++) {
    serialOutputs[inds] = 0;
  }

  // -- Inactivate all extra timers --
  for (indt=0; indt < MAXNEXTRATIMERS; indt++) {
    activeExtraTimers[indt] = false;
  }

  // -- Connect to client --
  establishConnection();
}

void setup() {
  Serial.begin(115200);  // Connection to client
  SerialUSB.begin(115200); // Serial output (for sound-module, for example)
  // NOTE: is the baud rate ignored for usb virtual serial?
  initialize();  // As a function, in case we need to re-initialize
}

void add_event(int thisEventCode) {
      // eventsTime[nEvents] = micros(); // DEBUG (test jumpy button)
      eventsTime[nEvents] = millis();
      eventsCode[nEvents] = thisEventCode;
      nEvents++;
      eventsToProcess++;
  
}

// Read inputs and change state accordingly
void execute_cycle() {

  // -- Check for any changes in inputs --
  for (indi = 0; indi < nInputs; indi++) {
    previousValue = inputValues[indi];
#ifdef HARDWARE_TEST
    inputValues[indi] = !digitalRead(inputPins[indi]);  // XXFIXME: DEBUG: inverting signals
#else
    inputValues[indi] = digitalRead(inputPins[indi]);
#endif
    if (inputValues[indi]!=previousValue) {
      // The codes are as follows:
      // For input0: 0=up, 1=down, for input1: 2=up, 3=down
      add_event(2*indi + previousValue);
    }
  }
  
  // -- Test if the state timer finished --
  currentTime = millis();
  if(currentTime-stateTimerValue >= stateTimers[currentState]) {
    add_event(2*nInputs);
    stateTimerValue = currentTime; // Restart timer
  }
  // XXFIXME: is this the right way to reset the timer?


  // -- Test if any extra timer finished --
  for (indt=0; indt < nExtraTimers; indt++) {
    if (activeExtraTimers[indt]) {
      if(currentTime-extraTimersValues[indt] >= extraTimers[indt]) {
	add_event(2*nInputs+1+indt);
	activeExtraTimers[indt] = false;
      }
    }
  }

  // -- Update state machine given last events --
  previousState = currentState;
  update_state_machine();    // Updates currentState
  if (currentState != previousState) {
    enter_state(currentState);
  }

}


// -- Execute when entering a state --
void enter_state(unsigned char newState) {
  stateTimerValue = millis();

  // -- Start extra timers --
  for (indt=0; indt < nExtraTimers; indt++) {
    if (triggerStateEachExtraTimer[indt]==newState) {
      extraTimersValues[indt] = millis();
      activeExtraTimers[indt] = true;
    }
  }

  // -- Change outputs according to new state --
  for (indo = 0; indo < nOutputs; indo++) {
    // -- Do not change outputs set to anything different from 0 or 1 --
    if (stateOutputs[newState][indo]==1) {
	digitalWrite(outputPins[indo],HIGH);
    }
    else if (stateOutputs[newState][indo]==0) {
	digitalWrite(outputPins[indo],LOW);
    }
  }

  // -- Send output through SerialUSB --
  if (serialOutputs[newState]) {
    SerialUSB.write(serialOutputs[newState]);
  }

}

// -- Update state machine according to events in queue --
void update_state_machine() {
  int currentEventIndex;
  int currentEvent;
  //for (inde=eventsToProcess; inde>0; inde--) {
  while (eventsToProcess>0) {
    currentEventIndex = nEvents-eventsToProcess;
    currentEvent = eventsCode[currentEventIndex];
    nextState[currentEventIndex] = stateMatrix[currentState][currentEvent];
    currentState = nextState[currentEventIndex];
    eventsToProcess--;
  }
}

unsigned long read_uint32_serial() {
  // Read four bytes and combine them (little endian order, LSB first)
  unsigned long value=0;
  int ind;
  for (ind=0; ind<4; ind++)
  {
    while (!Serial.available()) {}  // Wait for data
    serialByte = Serial.read();
      value = ((unsigned long) serialByte << (8*ind)) | value;
  }
  return value;
}


void loop(){
  //digitalWrite(ledPin, LOW);  // DEBUG
  if (runningState) {
      execute_cycle();
  }
  while (Serial.available()>0) {
    serialByte = Serial.read();
    switch(serialByte) {
      case TEST_CONNECTION: {
	Serial.write(OK);
	break;
      }
      case GET_SERVER_VERSION: {
	Serial.println(VERSION);
	break;
      }
      case SET_SIZES: {
	while (!Serial.available()) {}  // Wait for data
	nInputs = Serial.read();
	while (!Serial.available()) {}  // Wait for data
	nOutputs = Serial.read();
	while (!Serial.available()) {}  // Wait for data
	nExtraTimers = Serial.read();
	nActions = 2*nInputs + 1 + nExtraTimers;
	sizesSetFlag = true;
	break;
      }
      case GET_TIME: {
	eventTime = millis();
	Serial.println(eventTime);
	break;
      }
      case GET_INPUTS: {
	Serial.write(nInputs);
	for (indi = 0; indi < nInputs; indi++) {
	  Serial.write(inputValues[indi]);
	}
	break;
      }
      case FORCE_OUTPUT: {
	// XXFIXME: this must change given the new way of dealing with outputs
	//        and I should check if nOutputs have been defined.
	while (!Serial.available()) {} // Wait for data
	indo = Serial.read();          // Read the output index
	while (!Serial.available()) {} // Wait for data
	serialByte = Serial.read();    // Read the output value
	if (indo<MAXNOUTPUTS) {
	    digitalWrite(outputPins[indo],serialByte);
	}
	break;
      }
      case SET_STATE_MATRIX: {
	// NOTE: indRow,indCol are 'char', limiting the matrix to size 256x256
	unsigned int indRow,indCol;
	while (!Serial.available()) {}  // Wait for data
	nStates = Serial.read();
	while (!Serial.available()) {}  // Wait for data
	serialByte = Serial.read(); // Should be equal to nActions
	if (serialByte!=nActions) {
	  Serial.write(ERROR);
	  Serial.println('The number of columns does not correspond to nActions.');
        }
	for (indRow=0;indRow<nStates;indRow++) {
	  for (indCol=0;indCol<nActions;indCol++) {
	    while (!Serial.available()) {}  // Wait for data
	    stateMatrix[indRow][indCol] = Serial.read();
	  }
	}
	break;
      }
      case REPORT_STATE_MATRIX: {
	// --- Send matrix back ---
	int indRow,indCol;
	for (indRow=0;indRow<nStates;indRow++) {
	  for (indCol=0;indCol<nActions;indCol++) {
	    Serial.print(stateMatrix[indRow][indCol], DEC);
	    Serial.print("  ");
	  }
	  Serial.print("\n");
	}
	break;
      }
      case RUN: {
	runningState = true;
	//enable_interrupts();
	break;
      }
      case STOP: {
	runningState = false;
	//disable_interrupts();
	break;
      }
      case SET_STATE_TIMERS: {
	for (inds=0; inds<nStates; inds++) {
	  stateTimers[inds] = read_uint32_serial();
	}
	break;
      }
      case REPORT_STATE_TIMERS: {
	for (inds=0; inds<nStates; inds++) {
	  Serial.print(stateTimers[inds]);
	  Serial.print('\n');
	}	
	break;
      }
      case SET_EXTRA_TIMERS: {
	for (indt=0; indt<nExtraTimers; indt++) {
	  extraTimers[indt] = read_uint32_serial();
	}
	break;
      }
      case SET_EXTRA_TRIGGERS: {
	for (indt=0; indt<nExtraTimers; indt++) {
	  while (!Serial.available()) {}  // Wait for data
	  triggerStateEachExtraTimer[indt] = Serial.read();
	}
	break;
      }
      case REPORT_EXTRA_TIMERS: {
	for (indt=0; indt<nExtraTimers; indt++) {
	  Serial.print(triggerStateEachExtraTimer[indt]);
	  Serial.print(" " );
	  Serial.println(extraTimers[indt]);
	}	
	break;
      }
      case SET_STATE_OUTPUTS: {
	unsigned int indRow,indCol;
	while (!Serial.available()) {}  // Wait for data
	nStates = Serial.read();
	while (!Serial.available()) {}  // Wait for data
	nOutputs = Serial.read();
	for (indRow=0;indRow<nStates;indRow++) {
	  for (indCol=0;indCol<nOutputs;indCol++) {
	    while (!Serial.available()) {}  // Wait for data
	    stateOutputs[indRow][indCol] = Serial.read();
	  }
	}
	break;
      }
      case SET_SERIAL_OUTPUTS: {
	for (inds=0; inds<nStates; inds++) {
	  while (!Serial.available()) {}  // Wait for data
	  serialOutputs[inds] = Serial.read();
	}
	break;
      }
      case REPORT_SERIAL_OUTPUTS: {
	for (inds=0; inds<nStates; inds++) {
	  Serial.print(serialOutputs[inds],DEC);
	  Serial.print(' ');
	}
	Serial.print('\n');
	break;
      }
      case GET_EVENTS: {
	Serial.write((char) nEvents); // XXFIXME: this limits it to 256
	for (inde=0; inde < nEvents; inde++) {
	  Serial.print(eventsTime[inde]);
	  Serial.print(" ");
	  Serial.print(eventsCode[inde]);
	  Serial.print(" ");
	  Serial.print(nextState[inde]);
	  Serial.print("\n");
	}
	nEvents=0;
	break;
      }
      case GET_CURRENT_STATE: {
	Serial.write(currentState);
	break;
      }
      case FORCE_STATE: {
	eventsTime[nEvents] = millis();
	while (!Serial.available()) {}  // Wait for data
	currentState = Serial.read();
	eventsCode[nEvents] = -1;
	nextState[nEvents] = currentState;
	nEvents++;
	enter_state(currentState);
	break;
      }
      default: {
	Serial.write(ERROR);
	Serial.write(serialByte);
	break;
      }
    }
  }
}

