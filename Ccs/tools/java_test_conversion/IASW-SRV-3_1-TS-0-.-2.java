package pl_cbk_fgs_ariel.ut;

import simtg.simops.base.SimopsException;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import pl_cbk_fgs_ariel.common.PlCbkFgsArielTestSequence;
import pl_cbk_fgs_ariel.common.TcPusPkt;
import pl_cbk_fgs_ariel.common.TmPusPkt;
import simtg.simops.plugin.spacewire.SpwPlugin;
import simtg.simops.plugin.spacewire.SpwSeqPlugin;
import simtg.simops.plugin.spacewire.SpwSpyDynamic;
import simtg.simops.plugin.spacewire.SpwSpyPacket;
import simtg.simops.plugin.spacewire.SpwSeqPlugin;

public class IASW_SRV_3_1_TS_02 extends PlCbkFgsArielTestSequence {

    public static void main(String[] args) {
        new IASW_SRV_3_1_TS_02().run();
    }

    @Override
    public void sequence() throws SimopsException {
        tester.logSection("Start of test");
        {
            createDpuBench();
			getSpwN().bind("stubSpwN");
			getSpwR().bind("stubSpwR");
			SpwSpyDynamic spySpwN = getSpwN().getSpyManager().addSpyBuffer("mySpy");
			SpwSpyDynamic spySpwR = getSpwR().getSpyManager().addSpyBuffer("mySpy");

			getSpwN().connect(dpuName + ".SPWN");
			getSpwR().connect(dpuName + ".SPWR");

            tester.logStep("Init model");
            sim.init();

            tester.logStep("Testing Boot");
			sim.writeBoolean(dpuName + ".In.pwrN", true);
			sim.activateMethod(dpuName + ".BootSwHandover");
			
			
			sim.timeStep(15.0);
			
			sim.timeStep(15.0);
			
			sim.timeStep(3.0);
			

			getSpwN().isLinkStarted();

            SpwSpyPacket spwPkt = spySpwN.getPacket();
            byte[] data = spwPkt.getData();

            byte[] pkt = new byte[1032];
        
            sim.insertLog("#--------------------------------------------");
            sim.insertLog("# IASW-SRV-3_1");
            sim.insertLog("# Test to verify the functionality of Service 3 Housekeeping Data Reporting Service");
            sim.insertLog("# Specification Version: 0.2");
            sim.insertLog("# Software Version: ");
            sim.insertLog("# Author: UVIE");
            sim.insertLog("# Date: 2025-05-05");
            sim.insertLog("#--------------------------------------------");
            sim.insertLog("# COMMENT: ");
            sim.insertLog("PRECONDITIONS: IASW in STANDBY mode");

            tester.logStep("STEP 1.0");
            sim.insertLog("Send TC(3,5) with SID 2 to enable the extended HK");

            tester.logStep("STEP 2.0");
            sim.insertLog("Wait for TM(3,25) with SID 2");
            sim.insertLog("VERIFICATION: TM(3,25) with SID 2 received every 4 seconds");

            tester.logStep("STEP 3.0");
            sim.insertLog("Send TC(3,31) with SID 2 and a period X to change the generation period of the extended HK");

            tester.logStep("STEP 4.0");
            sim.insertLog("Wait for TM(3,25) with SID 2");
            sim.insertLog("VERIFICATION: TM(3,25) with SID 2 is received every X");

            tester.logStep("STEP 5.0");
            sim.insertLog("Send TC(3,31) with SID 2 and period 0 to attempt to change the period to an illegal value");
            sim.insertLog("VERIFICATION: TM(1,4) received with failure code ACK_ILL_PER");

            tester.logStep("STEP 6.0");
            sim.insertLog("Send TC(3,6) with SID 2 to disable extended HK");

            tester.logStep("STEP 7.0");
            sim.insertLog("Wait for W seconds to verify that no TM(3,25) with SID 2 are received");
            sim.insertLog("VERIFICATION: No TM(3,25) with SID 2 received anymore");

            tester.logStep("STEP 8.0");
            sim.insertLog("Send TC(3,5) with SID 2 to re-enable extended HK");

            tester.logStep("STEP 9.0");
            sim.insertLog("Wait for TM(3,25) with SID 2");
            sim.insertLog("VERIFICATION: TM(3,25) with SID 2 received every X");
            sim.insertLog("# 
            sim.insertLog("COMMENT: The period change was kept");");

            tester.logStep("STEP 10.0");
            sim.insertLog("Send TC(3,6) with SID 2 to disable extended HK again");

            tester.logStep("STEP 11.0");
            sim.insertLog("Send TC(3,1) with SID 4 and at least one wrong Parameter ID");
            sim.insertLog("VERIFICATION: TM(1,4) received with failure code ACK_ILL_PID");

            tester.logStep("STEP 12.0");
            sim.insertLog("Send TC(3,1) with SID 4, some PID and period Y to create a new periodic HK");

            tester.logStep("STEP 13.0");
            sim.insertLog("Send TC(3,5) with SID 4 to enable new periodic HK");

            tester.logStep("STEP 14.0");
            sim.insertLog("Wait for TM(3,25) with SID 4");
            sim.insertLog("VERIFICATION: TM(3,25) with SID 4 received every Y");

            tester.logStep("STEP 15.0");
            sim.insertLog("Send TC(3,29) with SID 4 and some new PID to add items to an existing HK report");

            tester.logStep("STEP 16.0");
            sim.insertLog("Wait for TM(3,25) with SID 4");
            sim.insertLog("VERIFICATION: TM(3,25) with SID 4 received every Y and containing newly added item");

            tester.logStep("STEP 17.0");
            sim.insertLog("Send TC(3,1) with already used SID 4");
            sim.insertLog("VERIFICATION: TM(1,1) received and TM(1,4) received with failure code ACK_SID_IN_USE");

            tester.logStep("STEP 18.0");
            sim.insertLog("Send TC(3,3) with SID 4 to attempt to delete currently active HK report");
            sim.insertLog("VERIFICATION: TM(1,1) received and TM(1,4) received with failure code ACK_SID_IN_USE and TM(3,25) with SID 4 still received every Y");

            tester.logStep("STEP 19.0");
            sim.insertLog("Send TC(3,6) with SID 4 to disable HK report");

            tester.logStep("STEP 20.0");
            sim.insertLog("Send TC(3,9) with SID 4 to get Housekeeping Parameter Report Definitions Report");

            tester.logStep("STEP 21.0");
            sim.insertLog("Wait for TM(3,10) with SID 4");
            sim.insertLog("VERIFICATION: TM(3,10) received with SID 4 and parameter identifiers from all parameters in original definition and later addition");

            tester.logStep("STEP 22.0");
            sim.insertLog("Send TC(3,27) with SID 4 to request a one shot report");

            tester.logStep("STEP 23.0");
            sim.insertLog("Wait for TM(3,25) with SID 4");
            sim.insertLog("VERIFICATION: TM(3,25) with SID 4 received only once");

            tester.logStep("STEP 24.0");
            sim.insertLog("Send TM(3,3) with SID 4 to delete the HK report");

            tester.logStep("STEP 25.0");
            sim.insertLog("Send TC(3,1) with SID 4, period Y and some new PID");
            sim.insertLog("# 
            sim.insertLog("COMMENT: also shows that previous HK SID 4 was fully deleted");");

            tester.logStep("STEP 26.0");
            sim.insertLog("Send TC(3,5) with SID 4 to enable new periodic HK");

            tester.logStep("STEP 27.0");
            sim.insertLog("Wait for TM(3,25) with SID 4");
            sim.insertLog("VERIFICATION: TM(3,25) with SID 4 received once cotaining only the new PID");

            tester.logStep("STEP 28.0");
            sim.insertLog("Send TC(3,1) with SID 5 and to many PIDs");
            sim.insertLog("VERIFICATION: TM(1,4) received with failure code ACK_ILL_DSIZE");

            tester.logStep("STEP 29.0");
            sim.insertLog("Send TC(3,3) with SID 5 to attempt to interact with non existent SID");
            sim.insertLog("VERIFICATION: TM(1,1) received and TM(1,4) received with failure code ACK_SID_NOT_USED");

            tester.logStep("STEP 30.0");
            sim.insertLog("Send TC(3,5) with SID 5 to attempt to interact with non existent SID");
            sim.insertLog("VERIFICATION: TM(1,1) received and TM(1,4) received with failure code ACK_SID_NOT_USED");

            tester.logStep("STEP 31.0");
            sim.insertLog("Send TC(3,6) with SID 5 to attempt to interact with non existent SID");
            sim.insertLog("VERIFICATION: TM(1,1) received and TM(1,4) received with failure code ACK_SID_NOT_USED");

            tester.logStep("STEP 32.0");
            sim.insertLog("Send TC(3,9) with SID 5 to attempt to interact with non existent SID");
            sim.insertLog("VERIFICATION: TM(1,1) received and TM(1,4) received with failure code ACK_SID_NOT_USED");

            tester.logStep("STEP 33.0");
            sim.insertLog("Send TC(3,29) with SID 5 to attempt to interact with non existent SID");
            sim.insertLog("VERIFICATION: TM(1,1) received and TM(1,4) received with failure code ACK_SID_NOT_USED");

            tester.logStep("STEP 34.0");
            sim.insertLog("Send TC(3,31) with SID 5 to attempt to interact with non existent SID");
            sim.insertLog("VERIFICATION: TM(1,1) received and TM(1,4) received with failure code ACK_SID_NOT_USED");

            tester.logStep("STEP 35.0");
            sim.insertLog("Send TC(3,1) with SID > SID_MAX");
            sim.insertLog("VERIFICATION: TM(1,4) received with failure code ACK_ILL_SID");

            tester.logStep("STEP 36.0");
            sim.insertLog("Send TC(3,3) with SID > SID_MAX");
            sim.insertLog("VERIFICATION: TM(1,4) received with failure code ACK_ILL_SID");

            tester.logStep("STEP 37.0");
            sim.insertLog("Send TC(3,5) with SID > SID_MAX");
            sim.insertLog("VERIFICATION: TM(1,4) received with failure code ACK_ILL_SID");

            tester.logStep("STEP 38.0");
            sim.insertLog("Send TC(3,6) with SID > SID_MAX");
            sim.insertLog("VERIFICATION: TM(1,4) received with failure code ACK_ILL_SID");

            tester.logStep("STEP 39.0");
            sim.insertLog("Send TC(3,9) with SID > SID_MAX");
            sim.insertLog("VERIFICATION: TM(1,4) received with failure code ACK_ILL_SID");

            tester.logStep("STEP 40.0");
            sim.insertLog("Send TC(3,29) with SID > SID_MAX");
            sim.insertLog("VERIFICATION: TM(1,4) received with failure code ACK_ILL_SID");

            tester.logStep("STEP 41.0");
            sim.insertLog("Send TC(3,31) with SID > SID_MAX");
            sim.insertLog("VERIFICATION: TM(1,4) received with failure code ACK_ILL_SID");

            tester.logStep("STEP 42.0");
            sim.insertLog("Send many TC(3,1) with new SIDs to fill the RDL");
            sim.insertLog("VERIFICATION: TM(1,1) received and TM(1,4) received with failure code ACK_RDL_NO_SLOT once all slots are used up");
            sim.insertLog("POSTCONDITIONS
# IASW in STANDBY mode
");