/* 
 * File:   LX3302_capture_IC_Output.c
 * Author: 
 *
 * Created on October 25, 2019, 3:07 PM
 */
#include <system.h>
#include <stdint.h>
#include <string.h>
#include <stddef.h>
#include "LX3302_capture_IC_Output.h"
#include "LX3302_CCPModule.h"
#include <stdlib.h>

#define _XTAL_FREQ  48000000

char configbits[256];
uint16_t captureValue[30];

/*******************************************************************/

char capture_done = 0;
uint16_t capture_count = 0;
char edgeChange = 2;
int edgenum;
SENT_Frame get_SENTData(void)
{
	return sentFrameObj;
}
void interrupt low_priority capture() {
    NOP();
    if ((PIR4bits.CCP4IF == 1)&&(PIE4bits.CCP4IE == 1)) // CCP2IF is set when the falling edge is detected in CCP2 
    {
        PIR4bits.CCP4IF = 0; // clear the interrupt request flag 
        //rising edge interrupt
        if (capture_count < edgenum) {
            captureValue[capture_count] = CCPR4H * 256 + CCPR4L;
            capture_count++;
            if (edgeChange == 1) {
                //change to falling edge
                edgeChange = 0;
                CCP4CONbits.CCP4M = 0x04;
                //there is a false interrupt caused by edging change.
                //we have to clear it before leaving.               
                PIR4bits.CCP4IF = 0; // clear the interrupt request flag   
            } else if (edgeChange == 0) {
                //change to rising edge
                edgeChange = 1;
                CCP4CONbits.CCP4M = 0x05;
                //there is a false interrupt caused by edging change.
                //we have to clear it before leaving.               
                PIR4bits.CCP4IF = 0; // clear the interrupt request flag   
            }
        } else capture_done = 1;

    } else if ((PIE4bits.CCP9IE == 1) &&(PIR4bits.CCP9IF == 1)) {
        PIR4bits.CCP9IF = 0; // clear the interrupt request flag 
        //rising edge interrupt
        if (capture_count < edgenum) {
            captureValue[capture_count] = CCPR9H * 256 + CCPR9L;
            capture_count++;
            if (edgeChange == 1) {
                //change to falling edge
                edgeChange = 0;
                CCP9CONbits.CCP9M = 0x04;
                //there is a false interrupt caused by edging change.
                //we have to clear it before leaving.               
                PIR4bits.CCP9IF = 0; // clear the interrupt request flag   
            } else if (edgeChange == 0) {
                //change to rising edge
                edgeChange = 1;
                CCP9CONbits.CCP9M = 0x05;
                //there is a false interrupt caused by edging change.
                //we have to clear it before leaving.               
                PIR4bits.CCP9IF = 0; // clear the interrupt request flag   
            }
        } else capture_done = 1;
    } else if ((PIE1bits.CCP1IE == 1) &&(PIR1bits.CCP1IF == 1)) {
        PIR1bits.CCP1IF = 0; // clear the interrupt request flag 
        //rising edge interrupt
        if (capture_count < edgenum) {
            captureValue[capture_count] = CCPR1H * 256 + CCPR1L;
            capture_count++;
            if (edgeChange == 1) {
                //change to falling edge
                edgeChange = 0;
                CCP1CONbits.CCP1M = 0x04;
                //there is a false interrupt caused by edging change.
                //we have to clear it before leaving.               
                PIR1bits.CCP1IF = 0; // clear the interrupt request flag   
            } else if (edgeChange == 0) {
                //change to rising edge
                edgeChange = 1;
                CCP1CONbits.CCP1M = 0x05;
                //there is a false interrupt caused by edging change.
                //we have to clear it before leaving.               
                PIR1bits.CCP1IF = 0; // clear the interrupt request flag   
            }
        } else capture_done = 1;
    }
}

void convertTC2Period(int num) {
    for (int i = 1; i < num; i++) {
        if (captureValue[i] > captureValue[i - 1])
            captureValue[i - 1] = captureValue[i] - captureValue[i - 1];
        else {
            //overflow
            captureValue[i - 1] = 0xFFFF - captureValue[i - 1] + captureValue[i];
        }
    }
}

/*Purpose : findout the sync pulse out of the captured data.
 *  Description : once the 21 data captures are done, take the first data and 
 * assume it as sync pulse(sync pulse contains 56 clock ticks), find what is
 * clock tick value by divide the first data with 56, Once the tick value is 
 * calculated , use the tick value and find out the number of clock ticks in other data
 * If the clock ticks are in between 12 to 27, then sync pulse is determined, otherwise 
 * take the next data, and repeat the above for rest of the 21 captured falling edge data
 * until the sync pulse is determined. 
 * Note : other than sync pulse, none of the data takes more than 27 clock ticks and less
 *  than 12 clock ticks.
 */
int findFirstSyncpulse() {
    int i, j;
    unsigned int One_clock_tick_value, num_clock_ticks_In_nibble;
    unsigned int remainder_to_adj_fraction;

    for (i = 0; i < 10; i++)//without pause pulse, 9 pulses/SENT frame
    {
        One_clock_tick_value = 0;
        num_clock_ticks_In_nibble = 0;
        remainder_to_adj_fraction = 0;

        /*the value of one clock tick*/
        One_clock_tick_value = captureValue[i] / 56;
        /*Since it is integer division, remainder is calculated to adjust*/
        remainder_to_adj_fraction = captureValue[i] % 56;

        if (remainder_to_adj_fraction * 2 > 56) One_clock_tick_value++;
        if (One_clock_tick_value == 0) continue;

        remainder_to_adj_fraction = 0;
        for (j = 1; j < 9; j++) {
            num_clock_ticks_In_nibble = captureValue[i + j] / One_clock_tick_value;
            remainder_to_adj_fraction = captureValue[i + j] % One_clock_tick_value;

            if (2 * remainder_to_adj_fraction > One_clock_tick_value) num_clock_ticks_In_nibble++;
            if ((num_clock_ticks_In_nibble < 12) || (num_clock_ticks_In_nibble > 27)) break;
        }
        if (j == 9) {
            //find the sync pulse
            break;
        }
    }
    return i;
}
/**757
 * 
 * @param base: first ascii char index of configbits array
 * @param start: first sync pulse TV index of captureValue array
 * @param packtsNumber: num of SENT packets data will be converted
 * @return 
 */

char crc_table[] = {0, 13, 7, 10, 14, 3, 9, 4, 1, 12, 6, 11, 15, 2, 8, 5};

/*This function parses the SENT frame and extracts the Status, DATA123 and DATA456 and CRC*/
int convert2HexNibble(int base, int start, int packtsNumber) {

    char checksum, crc_cal, tblval;

    uint16_t i, j, counter56ticks, remainder_to_adj_fraction, numofticks;

    for (i = 0; i < packtsNumber; i++) {
        counter56ticks = captureValue[start + i * 9]; //9 pulses/SENT data packet for 3302, no pause pulse
        checksum = 5; //seed
        for (j = 0; j < 8; j++) //decode to Hex nibble value.
        { //S&C,S1D1,S1D2,S1D3,S2D1,S2D2,S2D3,CRC
            //9 pulses/SENT data packet for 3302, no pause pulse
            numofticks = captureValue[i * 9 + start + j + 1] * 56 / counter56ticks;
            remainder_to_adj_fraction = (captureValue[i * 9 + start + j + 1] * 56) % counter56ticks;
            if (2 * remainder_to_adj_fraction > counter56ticks) numofticks += 1;
            configbits[i * 10 + base + j] = numofticks - 12;
            if ((j > 0)&&(j < 7)) {
                tblval = crc_table[checksum];                
                checksum = configbits[i * 10 + base + j] ^ tblval;
            }
        }
        tblval = crc_table[checksum];   
        crc_cal = 0 ^ tblval;
        if (crc_cal != configbits[i * 10 + base + 7]) {
            //crc failed
            NOP();
            return -1;
        }
		
		sentFrameObj.Status = configbits[0];
		sentFrameObj.nibble_123 = configbits[1]<<8 | configbits[2]<<4 |configbits[3];
		sentFrameObj.nibble_456 = configbits[4]<<8 | configbits[5]<<4 |configbits[6];
		sentFrameObj.CRC = configbits[7];		
#if 0        
        for (j = 0; j < 8; j++)
            Convert1AsciiD(i * 10 + base + j); //convert and save starting at 0

        configbits[i * 10 + base + 8] = 0x0D; //order important for Win textbox
        configbits[i * 10 + base + 9] = 0x0A;
#endif
    }
    return 0;
}
/*This fucntion is required when USB communciation is used to send data onto GUI or any other purpose*/
void Convert1AsciiD(int addr) { //converts 0-15 to ascii character
    uint8_t x;
    x = configbits[addr];
    if ((x & 0xf) < 10) //bits 3-0
    {
        configbits[addr] = (x & 0xf) + 48;
    }//ascii 0-9
    else {
        configbits[addr] = (x & 0xf) + 55;
    } //ascii A-F
}

int SENT_multiFrames(uint8_t IO_Selected, uint8_t numFrame) {
    uint8_t enable_interrupt;
    int FirstSyncPulseIndex;
    int i, bytes;
    int time = 0;

    enable_interrupt = PIE2bits.USBIE; //save USB interrupt config;
    PIE2bits.USBIE = 0; //disable USB interrupt, re-enable once the data is captured.
    OSCCON = 0x70; // 01110000; system clock - 12MHz 
    capture_count = 0;
    capture_done = 0;
    edgenum = (numFrame + 1)*10 + 1; //capture 21 falling edges(20 pulses: guarantee to include one full SENT frame pulses)

    memset(captureValue, 0, sizeof (captureValue));

    /*Configure the CCP modules for respective IO to 
     * capture SENT data output from IC Note: Data parsing is done in GUI software*/
    if (IO_Selected == 1)
        CCP1_IO1SENT();
    else if (IO_Selected == 2)
        CCP9_IO2_SENT();
    else if (IO_Selected == 3)
        CCP4_IO3_SENT();
    
    do // wait loop 
    {
        __delay_us(1000);
        time++;
    } while ((!capture_done) && (time < 500));

    PIE2bits.USBIE = enable_interrupt;

    PIE4bits.CCP4IE = 0; // CCP4 interrupt disabled  
    PIE4bits.CCP9IE = 0; // CCP9 interrupt disabled  
    PIE1bits.CCP1IE = 0; // CCP1 interrupt disabled       
    T1CONbits.TMR1ON = 0;

    if (time == 500) {
        NOP();
        return -1; //timeout  
    }

    convertTC2Period(edgenum);

    FirstSyncPulseIndex = findFirstSyncpulse();
    if (FirstSyncPulseIndex > 9) {
        NOP();
        return -2; //could not find sync pulse         
    }
    if (-1 == convert2HexNibble(0, FirstSyncPulseIndex, numFrame)) {
        NOP();
        return -3; //crc error
    }


    /*The below code is optional, if you are designing any GUI with USB communication use this, it is sending STATUS, NIBBLE 123 and 456 along CRC
	Otherwise not using USB communication, can print array configbits with size of varaible bytes is calculated*/
    
    //configbits[0--9] is the hex data(asccii)
    bytes = 10 * numFrame;
     //wrap_putUSBUSART(configbits,bytes);
    return 0;
}
void main(void)
{
	SENT_Frame obj;
	if(0 == SENT_multiFrames(IO3,1);
	{
		obj = get_SENTData();
	}
	else{
		/*Set an Error*/
	}
}