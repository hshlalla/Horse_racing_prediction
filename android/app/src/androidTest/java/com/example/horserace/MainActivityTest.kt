package com.example.horserace

import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.Assert.*

@RunWith(AndroidJUnit4::class)
class MainActivityTest {
    @Test
    fun testActivityLaunches() {
        // Launch the activity
        val scenario = ActivityScenario.launch(MainActivity::class.java)
        
        // Basic smoke test to ensure no crash on launch
        scenario.onActivity { activity ->
            assertNotNull(activity)
        }
    }
}
