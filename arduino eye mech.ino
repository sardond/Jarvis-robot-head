#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

/* ================== SERVO LIMITS ================== */
#define SERVOMIN 150
#define SERVOMAX 600

/* ================== EYELID OPEN / CLOSE ================== */
int LU_OPEN  = 345; int LU_CLOSE = 432;
int LL_OPEN  = 331; int LL_CLOSE = 226;
int RU_OPEN  = 303; int RU_CLOSE = 226;
int RL_OPEN  = 354; int RL_CLOSE = 468;

/* ================== EYE CENTERS ================== */
int LR_CENTER = 322;
int UD_CENTER = 355;

/* ================== SERVO CHANNELS ================== */
#define CH_LR     0
#define CH_UD     1
#define CH_LU     2
#define CH_LL     3
#define CH_RU     4
#define CH_RL     5
#define CH_SWIVEL 6  // HEAD SERVO

/* ================== STATE SYSTEM ================== */
enum SystemState { AWAKE, SLEEPING };
SystemState currentState = AWAKE;

/* ================== LID FOLLOW ================== */
int lidFollowAmount = 15;
int DIR_LU = +1; int DIR_LL = +1;
int DIR_RU = -1; int DIR_RL = -1;

/* ================== HEAD (SWIVEL) CONFIG ================== */
int swivelAngle = 90;
const int swivelMin = 45;
const int swivelMax = 135;
const int swivelCenter = 90;

// --- ADJUST THIS OFFSET TO ALIGN WITH TRIPOD ---
// Positive numbers turn head Right, Negative numbers turn head Left.
int swivelOffset = 4; 

const int swivelStepDeg = 1;
const unsigned long swivelUpdateInterval = 20;
unsigned long lastSwivelUpdate = 0;

// Eye extreme thresholds
const int eyeLeftStart  = LR_CENTER + 90;   
const int eyeLeftStop   = LR_CENTER + 60;   
const int eyeRightStart = LR_CENTER - 90;   
const int eyeRightStop  = LR_CENTER - 60;   

bool headTurningLeft = false;
bool headTurningRight = false;

/* ================== BLINK SYSTEM (V1) ================== */
enum BlinkState { IDLE, CLOSING, CLOSED, OPENING };
BlinkState blinkState = IDLE;
unsigned long blinkTimer = 0;
unsigned long blinkInterval = 0;
const int blinkSteps = 2;
const int blinkStepDelay = 2;
int blinkStep = 0;
bool doDoubleBlink = false;
int blinkStartLU, blinkStartLL;

/* ================== FUNCTIONS ================== */
void setLidsRaw(int LU, int LL) {
  int RU = RU_OPEN + (LU_OPEN - LU) * DIR_RU;
  int RL = RL_OPEN + (LL_OPEN - LL) * DIR_RL;
  pwm.setPWM(CH_LU, 0, LU);
  pwm.setPWM(CH_LL, 0, LL);
  pwm.setPWM(CH_RU, 0, RU);
  pwm.setPWM(CH_RL, 0, RL);
}

void eyelidsClosed() {
  pwm.setPWM(CH_LU, 0, LU_CLOSE);
  pwm.setPWM(CH_LL, 0, LL_CLOSE);
  pwm.setPWM(CH_RU, 0, RU_CLOSE);
  pwm.setPWM(CH_RL, 0, RL_CLOSE);
}

void updateSwivel(int eyePos) {
  if (millis() - lastSwivelUpdate < swivelUpdateInterval) return;
  lastSwivelUpdate = millis();

  if (eyePos > eyeLeftStart) { headTurningLeft = true; headTurningRight = false; }
  else if (eyePos < eyeRightStart) { headTurningRight = true; headTurningLeft = false; }

  if (eyePos < eyeLeftStop) headTurningLeft = false;
  if (eyePos > eyeRightStop) headTurningRight = false;

  if (headTurningLeft && swivelAngle > swivelMin) swivelAngle -= swivelStepDeg;
  else if (headTurningRight && swivelAngle < swivelMax) swivelAngle += swivelStepDeg;

  swivelAngle = constrain(swivelAngle, swivelMin, swivelMax);
  
  // Apply the offset here during the mapping
  int swivelPulse = map(swivelAngle + swivelOffset, 0, 180, SERVOMIN, SERVOMAX);
  pwm.setPWM(CH_SWIVEL, 0, swivelPulse);
}

/* ================== COOL V1 ANIMATIONS ================== */
void sleepAnimation() {
  for (int i = 0; i <= 15; i++) {
    int lu = map(i, 0, 15, LU_OPEN, (LU_OPEN + LU_CLOSE) / 2);
    int ll = map(i, 0, 15, LL_OPEN, (LL_OPEN + LL_CLOSE) / 2);
    int ru = map(i, 0, 15, RU_OPEN, (RU_OPEN + RU_CLOSE) / 2);
    int rl = map(i, 0, 15, RL_OPEN, (RL_OPEN + RL_CLOSE) / 2);
    pwm.setPWM(CH_LU, 0, lu); pwm.setPWM(CH_LL, 0, ll);
    pwm.setPWM(CH_RU, 0, ru); pwm.setPWM(CH_RL, 0, rl);
    delay(70);
  }
  delay(150);
  for (int i = 0; i <= 10; i++) {
    int lu = map(i, 0, 10, (LU_OPEN + LU_CLOSE) / 2, LU_OPEN + (LU_CLOSE - LU_OPEN) / 4);
    int ll = map(i, 0, 10, (LL_OPEN + LL_CLOSE) / 2, LL_OPEN + (LL_CLOSE - LL_OPEN) / 4);
    int ru = map(i, 0, 10, (RU_OPEN + RU_CLOSE) / 2, RU_OPEN + (RU_CLOSE - RU_OPEN) / 4);
    int rl = map(i, 0, 10, (RL_OPEN + RL_CLOSE) / 2, RL_OPEN + (RL_CLOSE - RL_OPEN) / 4);
    pwm.setPWM(CH_LU, 0, lu); pwm.setPWM(CH_LL, 0, ll);
    pwm.setPWM(CH_RU, 0, ru); pwm.setPWM(CH_RL, 0, rl);
    delay(60);
  }
  delay(200);
  for (int i = 0; i <= 25; i++) {
    int lu = map(i, 0, 25, LU_OPEN + (LU_CLOSE - LU_OPEN) / 4, LU_CLOSE);
    int ll = map(i, 0, 25, LL_OPEN + (LL_CLOSE - LL_OPEN) / 4, LL_CLOSE);
    int ru = map(i, 0, 25, RU_OPEN + (RU_CLOSE - RU_OPEN) / 4, RU_CLOSE);
    int rl = map(i, 0, 25, RL_OPEN + (RL_CLOSE - RL_OPEN) / 4, RL_CLOSE);
    pwm.setPWM(CH_LU, 0, lu); pwm.setPWM(CH_LL, 0, ll);
    pwm.setPWM(CH_RU, 0, ru); pwm.setPWM(CH_RL, 0, rl);
    delay(90);
  }
  eyelidsClosed();
}

void wakeAnimation() {
  eyelidsClosed();
  delay(300);
  for (int i = 0; i <= 20; i++) {
    int lu = map(i, 0, 20, LU_CLOSE, LU_OPEN);
    int ll = map(i, 0, 20, LL_CLOSE, LL_OPEN);
    int ru = map(i, 0, 20, RU_CLOSE, RU_OPEN);
    int rl = map(i, 0, 20, RL_CLOSE, RL_OPEN);
    pwm.setPWM(CH_LU, 0, lu); pwm.setPWM(CH_LL, 0, ll);
    pwm.setPWM(CH_RU, 0, ru); pwm.setPWM(CH_RL, 0, rl);
    delay(30);
  }
  for (int b = 0; b < 2; b++) {
    eyelidsClosed(); delay(150);
    setLidsRaw(LU_OPEN, LL_OPEN); delay(200);
  }
}

/* ================== SETUP ================== */
void setup() {
  Serial.begin(115200);
  pwm.begin();
  pwm.setPWMFreq(60);
  randomSeed(analogRead(A3));
  blinkInterval = random(3000, 7000);
  setLidsRaw(LU_OPEN, LL_OPEN);

  int centerPulse = map(swivelCenter + swivelOffset, 0, 180, SERVOMIN, SERVOMAX);
  pwm.setPWM(CH_SWIVEL, 0, centerPulse);
}

/* ================== LOOP ================== */
void loop() {
  static int faceX = 320;
  static int faceY = 240;
  unsigned long now = millis();

  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line == "SLEEP") { sleepAnimation(); currentState = SLEEPING; }
    else if (line == "WAKE") { wakeAnimation(); currentState = AWAKE; }
    else {
      int comma = line.indexOf(',');
      if (comma > 0 && currentState == AWAKE) {
        faceX = line.substring(0, comma).toInt();
        faceY = line.substring(comma + 1).toInt();
      }
    }
  }

  if (currentState == AWAKE) {
    int LR_pos = map(faceX, 0, 640, LR_CENTER + 120, LR_CENTER - 120);
    int UD_pos = map(faceY, 0, 480, UD_CENTER + 100, UD_CENTER - 100);
    pwm.setPWM(CH_LR, 0, LR_pos);
    pwm.setPWM(CH_UD, 0, UD_pos);

    updateSwivel(LR_pos);

    int offset = map(faceY, 0, 480, -lidFollowAmount, lidFollowAmount);
    int normalLU = LU_OPEN + offset * DIR_LU;
    int normalLL = LL_OPEN + offset * DIR_LL;

    switch (blinkState) {
      case IDLE:
        setLidsRaw(normalLU, normalLL);
        if (now - blinkTimer > blinkInterval) {
          blinkState = CLOSING; blinkTimer = now;
          blinkStartLU = normalLU; blinkStartLL = normalLL;
          blinkStep = 0;
        }
        break;
      case CLOSING:
        if (blinkStep < blinkSteps) {
          int lu = map(blinkStep, 0, blinkSteps, blinkStartLU, LU_CLOSE);
          int ll = map(blinkStep, 0, blinkSteps, blinkStartLL, LL_CLOSE);
          setLidsRaw(lu, ll); blinkStep++; delay(blinkStepDelay);
        } else { blinkState = CLOSED; blinkTimer = now; }
        break;
      case CLOSED:
        eyelidsClosed();
        if (now - blinkTimer > 150) { blinkState = OPENING; blinkStep = blinkSteps; }
        break;
      case OPENING:
        if (blinkStep > 0) {
          int lu = LU_CLOSE + (blinkStartLU - LU_CLOSE) * blinkStep / blinkSteps;
          int ll = LL_CLOSE + (blinkStartLL - LL_CLOSE) * blinkStep / blinkSteps;
          setLidsRaw(lu, ll); blinkStep--; delay(blinkStepDelay);
        } else {
          if (!doDoubleBlink && random(0, 100) < 25) { doDoubleBlink = true; blinkState = CLOSING; blinkStep = 0; }
          else { doDoubleBlink = false; blinkState = IDLE; blinkTimer = now; blinkInterval = random(3000, 7000); }
        }
        break;
    }
  } else { eyelidsClosed(); }
}
