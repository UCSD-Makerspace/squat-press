/* 
 * File:   LX3302_CCPModule.c
 * Author: 
 *
 * Created on October 17, 2019, 4:00 PM
 */

#include <stdio.h>
#include <stdlib.h>
#include <xc.h>
#include "LX3302_CCPModule.h"

extern char edgeChange;

void CCP1_IO1_SENT(void)
{
    //Unlock the Remap Peripheral(RP)
    EECON2 = 0x55;
    EECON2 = 0xAA;
    PPSCONbits.IOLOCK = 0;

    IO1_U1_DIRSET = CONFIG_PIN_AS_INPUT; // set RD2 as input for CCP1
    RPINR7 = 19; //RP19 as capture pin
    
    //Lock the Remap Peripheral (RP)
    EECON2 = 0x55;
    EECON2 = 0xAA;
    PPSCONbits.IOLOCK = 1;
    
    CCP1CON = 0x04;
    
    edgeChange = 2; // don't change edge in interrupt
    // CCP9 interrupt setup
    IPR1bits.CCP1IP = 0; // CCP4 interrupt set to low priority;
    PIR1bits.TMR1IF = 0; // clear the timer 1 interrupt flags 
    PIR1bits.CCP1IF = 0; // clear CCP4 interrupt flags 
    RCONbits.IPEN = 1; // interrupt priority enabled         

    //Select Timer1 for CCP1
    CCPTMRS0 = 0;

    T1CONbits.TMR1CS = 0; //timer 1 clock source is internal clock(Fosc/4))
    T1CONbits.T1CKPS0 = 0;
    T1CONbits.T1CKPS1 = 0; //timer 1 pre scale 1:1 
    T1CONbits.RD16 = 0; // use two 8-bit read/write operation
    TMR1H = 0x00; // clear timer1 
    TMR1L = 0x00;
    T1CONbits.TMR1ON = 1; // timer 1 enabled;

    // enable interrupts 
    INTCONbits.GIE = 1;
    INTCONbits.PEIE = 1;
    PIE1bits.CCP1IE = 1; // CCP9 interrupt enabled     
}
void CCP9_IO2_SENT(void) {
    IO2_U1_DIRSET = CONFIG_PIN_AS_INPUT; // set RC6 to input(CCP9);
    CCP9CON = 0x04;
    
    edgeChange = 2; // don't change edge in interrupt
    // CCP9 interrupt setup
    IPR4bits.CCP9IP = 0; // CCP4 interrupt set to low priority;
    PIR1bits.TMR1IF = 0; // clear the timer 1 interrupt flags 
    PIR4bits.CCP9IF = 0; // clear CCP4 interrupt flags 
    RCONbits.IPEN = 1; // interrupt priority enabled         

    CCPTMRS2 = 0;

    T1CONbits.TMR1CS = 0; //timer 1 clock source is internal clock(FOSC/4))
    T1CONbits.T1CKPS0 = 0;
    T1CONbits.T1CKPS1 = 0; //timer 1 pre-scale 1:1 
    T1CONbits.RD16 = 0; // use two 8-bit read/write operation
    TMR1H = 0x00; // clear timer1 
    TMR1L = 0x00;
    T1CONbits.TMR1ON = 1; // timer 1 enabled;

    // enable interrupts 
    INTCONbits.GIE = 1;
    INTCONbits.PEIE = 1;
    PIE4bits.CCP9IE = 1; // CCP9 interrupt enabled  
}

void CCP4_IO3_SENT(void) {
    IO3_U1_DIRSET = CONFIG_PIN_AS_INPUT; // set RB4 to input(CCP4); 

    // set CCP4 as capture mode, every falling edge    
    CCP4CON = 0x04;   

    edgeChange = 2; // don't change edge in interrupt
    // CCp4 interrupt setup
    IPR4bits.CCP4IP = 0; // CCP4 interrupt set to low priority;
    PIR1bits.TMR1IF = 0; // clear the timer 1 interrupt flags 
    PIR4bits.CCP4IF = 0; // clear CCP4 interrupt flags 
    RCONbits.IPEN = 1; // interrupt priority enabled     

    //timer1 setup
    CCPTMRS1 = 0;

    T1CONbits.TMR1CS = 0; //timer 1 clock source is internal clock(Fosc/4))
    T1CONbits.T1CKPS0 = 0;
    T1CONbits.T1CKPS1 = 0; //timer 1 prescale 1:1 
    T1CONbits.RD16 = 0; // use two 8-bit read/write operation
    TMR1H = 0x00; // clear timer1 
    TMR1L = 0x00;
    T1CONbits.TMR1ON = 1; // Timer1 enabled;

    // enable interrupts 
    INTCONbits.GIE = 1;
    INTCONbits.PEIE = 1;
    PIE4bits.CCP4IE = 1; // CCP4 interrupt enabled 
}