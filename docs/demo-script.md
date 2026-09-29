# GridTwin three-minute demo script

**Target length:** 3:00. **Start screen:** GridTwin dashboard, tab 1 (The story). **Demo setup:** Build and run the app using the [README](../README.md#run-it), confirm `/api/health` is healthy, and have the story data loaded before recording. The script assumes the default 10% voltage band and the all-homes solar case (S4).

The narration below is written to fit the timestamps at a conversational pace. Keep the cursor and transitions brisk; the time ranges include the clicks and screen changes.

| Time | On screen / action | Narration |
| --- | --- | --- |
| 0:00–0:25 | Open on **The story**. Point to the measured-voltage card. | “Before rooftop solar, voltage in Mathura is already close to the upper limit. In the smart-meter data, readings were above 253 volts 27.2% of the time, and the typical reading was 245.5 volts. GridTwin asks what happens when many homes add solar to a street like this.” |
| 0:25–0:45 | Click tab 2 (**Live map**) and point to the provenance labels at the bottom. | “The dashboard combines real household use and voltage measurements from Mathura with local weather. The street itself is a public benchmark adapted with Indian overhead wires. It is a transparent computer model for exploring the problem, not a surveyed utility feeder.” |
| 0:45–1:10 | On **The story**, point at the every-home solar result and recommended-fix cards. | “With solar on every modeled home, unsafe voltage lasts six and a half hours. Five hours and fifteen minutes are added by solar, and the peak reaches 263 volts. GridTwin then replays seven possible fixes over the whole day and checks whether they clear every unsafe interval.” |
| 1:10–1:40 | Click **Watch it happen on the live map**. Confirm S4, then press Play; pause around midday and point to the red buses and charts. | “Here we can watch the street at each 15-minute step. The map shows where voltage crosses the limit; the charts show voltage and the balance between solar generation and household demand. At midday, excess solar flows back into the street and pushes voltage up.” |
| 1:40–2:10 | Click tab 3 (**Fixes**). Choose **Tap +1 with inverter Volt/VAR** and play the side-by-side simulator. | “Now we apply a seasonal transformer tap adjustment and smart-inverter Volt/VAR together. Both maps replay the same day, so we can compare the result directly. In this case the combination clears the unsafe intervals without throwing away solar. The ranking also shows when no tested fix is safe.” |
| 2:10–2:35 | Click tab 4 (**AI forecast**). Show early-warning cards and prediction-versus-reality view. | “GridTwin also looks a day ahead. For 15 May 2025, the model predicted six hours and forty-five minutes of unsafe voltage; the replay using observed solar shows seven hours. Demand and upstream voltage use the same calendar day from 2019 as a labeled proxy, because that is the latest meter year available.” |
| 2:35–2:55 | Click tab 5 (**Hosting capacity**). Point to both capacity cards and the sweep chart. | “Finally, the hosting-capacity screen estimates how much solar fits under two different safety rules. In this modeled day, the no-new-fix estimate is 30 kilowatts; with the recommended setting changes it reaches 297 kilowatts. The estimate advances in 10% adoption steps, so this is a planning signal, not a connection approval.” |
| 2:55–3:00 | Return to the title/story header and hold. | “GridTwin helps utilities see the risk, test a response, and prepare before the voltage rises.” |

## Recording checklist

- Close unrelated tabs and terminals; use a readable browser zoom and hide personal notifications.
- Start the server before recording so first-load computation does not interrupt the narration.
- Wait for each screen to finish loading before recording that section. If the simulator loads slowly, pause the recording and resume once it is ready.
- Keep the demand-proxy and benchmark-feeder qualifications visible or spoken when those results are shown.
- If the live values differ from this script after data or model changes, use the values currently displayed in the app and update the narration before recording.
