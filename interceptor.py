import tkinter as tk
from tkinter import ttk, messagebox
import mido
import threading
import time
from collections import defaultdict

DEBUG_ENABLED = True

def debug_print(*args, **kwargs):
    if DEBUG_ENABLED:
        print(*args, **kwargs)

mido.set_backend('mido.backends.rtmidi')
midi_out = None

note_state = defaultdict(lambda: "none")
bounce_buffers = defaultdict(lambda: {"off": [], "on": []})

def handle_polytouch_bounce(msg, threshold):
    channel = getattr(msg, 'channel', 0)
    buffers = bounce_buffers[msg.note]

    if len(buffers["off"]) < 14:
        buffers["off"].append(msg.value)
    if len(buffers["off"]) == 14:
        diff_sum = (buffers["off"][1] - buffers["off"][0]) + (buffers["off"][3] - buffers["off"][2]) + (buffers["off"][5] - buffers["off"][4]) + (buffers["off"][7] - buffers["off"][6]) + (buffers["off"][9] - buffers["off"][8]) + (buffers["off"][11] - buffers["off"][10]) + (buffers["off"][13] - buffers["off"][12])
        debug_print(f"Off buffer diff for note {msg.note}: {diff_sum}")
        if diff_sum < 0:
            note_state[msg.note] = "none"
            note_off_msg = mido.Message('note_off', note=msg.note, velocity=0, channel=channel)
            debug_print(f"Bounce: Triggering note_off for note {msg.note}")
            if midi_out:
                midi_out.send(note_off_msg)
                return True
        buffers["on"].append(msg.value)
        if len(buffers["on"]) == 4:
            diff_sum = (buffers["on"][1] - buffers["on"][0]) + (buffers["on"][3] - buffers["on"][2]) 
            debug_print(f"On buffer diff for note {msg.note}: {diff_sum}")
            if diff_sum > 0:
                note_state[msg.note] = "artificial"
                note_on_msg = mido.Message('note_on', note=msg.note, velocity=min(127, msg.value), channel=channel)
                debug_print(f"Bounce: Triggering note_on for note {msg.note}")
                if midi_out:
                    midi_out.send(note_on_msg)
                    return True
            buffers["off"].clear()
            buffers["on"].clear()
    return False

def handle_message(msg, pass_polytouch_var, threshold_var, bounce_retrigger_var):
    debug_print(f"Incoming: {msg}")
    if msg.type == 'note_on':
        note_state[msg.note] = "real"
        if midi_out:
            midi_out.send(msg)
        bounce_buffers[msg.note]["off"].clear()
        bounce_buffers[msg.note]["on"].clear()
    elif msg.type == 'note_off':
        note_state[msg.note] = "none"
        if midi_out:
            midi_out.send(msg)
        bounce_buffers[msg.note]["off"].clear()
        bounce_buffers[msg.note]["on"].clear()
    elif msg.type == 'polytouch':
        if bounce_retrigger_var.get():
            if handle_polytouch_bounce(msg, threshold_var.get()):
                return
        current_state = note_state[msg.note]
        channel = getattr(msg, 'channel', 0)
        if current_state == "none":
            if msg.value > threshold_var.get():
                note_state[msg.note] = "artificial"
                artificial_on = mido.Message('note_on', note=msg.note, velocity=min(127, msg.value), channel=channel)
                debug_print(f"Artificial Note-On: {artificial_on}")
                bounce_buffers[msg.note]["off"].clear()
                bounce_buffers[msg.note]["on"].clear()
                if midi_out:
                    midi_out.send(artificial_on)
        elif current_state == "artificial":
            if msg.value < threshold_var.get():
                note_state[msg.note] = "none"
                artificial_off = mido.Message('note_off', note=msg.note, velocity=0, channel=channel)
                debug_print(f"Artificial Note-Off: {artificial_off}")
                bounce_buffers[msg.note]["off"].clear()
                bounce_buffers[msg.note]["on"].clear()
                if midi_out:
                    midi_out.send(artificial_off)
            else:
                if midi_out:
                    midi_out.send(msg)
                debug_print(f"Passing polytouch for artificial note {msg.note} (value={msg.value})")
        elif current_state == "real":
            if pass_polytouch_var.get():
                if midi_out:
                    midi_out.send(msg)
                debug_print(f"Passing polytouch for real note {msg.note} (value={msg.value})")
            else:
                debug_print(f"Ignoring polytouch for real note {msg.note}")
    else:
        if midi_out:
            midi_out.send(msg)
        debug_print(f"Passing through other MIDI message: {msg}")

def midi_loop(inport_name, stop_event, pass_polytouch_var, threshold_var, sleep_var, bounce_retrigger_var):
    try:
        with mido.open_input(inport_name) as inport:
            debug_print("MIDI input opened:", inport_name)
            while not stop_event.is_set():
                for msg in inport.iter_pending():
                    handle_message(msg, pass_polytouch_var, threshold_var, bounce_retrigger_var)
                time.sleep(sleep_var.get() / 1000.0)
    except Exception as e:
        debug_print("Error in MIDI loop:", e)

class MidiSelectorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MIDI Aftertouch -> Note-On Converter")
        self.geometry("400x550")
        self.midi_thread = None
        self.stop_event = threading.Event()
        self.pass_polytouch_var = tk.BooleanVar(value=False)
        self.bounce_retrigger_var = tk.BooleanVar(value=False)
        self.create_widgets()

    def create_widgets(self):
        midi_in_devices = mido.get_input_names() or ["No Input Devices Found"]
        midi_out_devices = mido.get_output_names() or ["No Output Devices Found"]

        tk.Label(self, text="Select MIDI Input Device:").pack(pady=5)
        self.combo_in = ttk.Combobox(self, values=midi_in_devices)
        self.combo_in.pack(pady=5)
        if midi_in_devices and midi_in_devices[0] != "No Input Devices Found":
            self.combo_in.current(0)

        tk.Label(self, text="Select MIDI Output Device:").pack(pady=5)
        self.combo_out = ttk.Combobox(self, values=midi_out_devices)
        self.combo_out.pack(pady=5)
        if midi_out_devices and midi_out_devices[0] != "No Output Devices Found":
            self.combo_out.current(0)

        self.check_polytouch = tk.Checkbutton(
            self,
            text="Pass polytouch for real/artificial notes",
            variable=self.pass_polytouch_var
        )
        self.check_polytouch.pack(pady=5)

        tk.Label(self, text="Threshold:").pack(pady=5)
        self.threshold_var = tk.IntVar(value=10)
        self.slider_thresh = tk.Scale(self, variable=self.threshold_var, from_=1, to=20, orient=tk.HORIZONTAL)
        self.slider_thresh.pack(pady=5)

        self.sleep_var = tk.IntVar(value=10)
        self.sleep_slider = tk.Scale(self, variable=self.sleep_var, from_=1, to=10, orient=tk.HORIZONTAL, label="Reaction (ms)")
        self.sleep_slider.pack(pady=5)

        self.start_button = tk.Button(self, text="Start", command=self.start_midi)
        self.start_button.pack(pady=10)

        self.stop_button = tk.Button(self, text="Stop", command=self.stop_midi, state=tk.DISABLED)
        self.stop_button.pack(pady=5)
        
        self.toggle_debug_button = tk.Button(self, text="Disable Debug Printing", command=self.toggle_debug)
        self.toggle_debug_button.pack(pady=5)

        self.toggle_bounce_button = tk.Button(self, text="Enable Bounce Retrigger", command=self.toggle_bounce)
        self.toggle_bounce_button.pack(pady=5)

    def toggle_debug(self):
        global DEBUG_ENABLED
        DEBUG_ENABLED = not DEBUG_ENABLED
        new_text = "Enable Debug Printing" if not DEBUG_ENABLED else "Disable Debug Printing"
        self.toggle_debug_button.config(text=new_text)
        debug_print("Debug printing toggled. Now:", DEBUG_ENABLED)

    def toggle_bounce(self):
        current = self.bounce_retrigger_var.get()
        self.bounce_retrigger_var.set(not current)
        new_text = "Disable Bounce Retrigger" if self.bounce_retrigger_var.get() else "Enable Bounce Retrigger"
        self.toggle_bounce_button.config(text=new_text)
        debug_print("Bounce Retrigger toggled. Now:", self.bounce_retrigger_var.get())

    def start_midi(self):
        in_device = self.combo_in.get()
        out_device = self.combo_out.get()
        if in_device == "No Input Devices Found" or not in_device:
            messagebox.showerror("Error", "No MIDI input device available!")
            return
        if out_device == "No Output Devices Found" or not out_device:
            messagebox.showerror("Error", "No MIDI output device available!")
            return
        global midi_out
        try:
            midi_out = mido.open_output(out_device)
            debug_print(f"MIDI output opened: {out_device}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open MIDI output: {e}")
            return
        self.stop_event.clear()
        self.midi_thread = threading.Thread(target=midi_loop, args=(
            in_device,
            self.stop_event,
            self.pass_polytouch_var,
            self.threshold_var,
            self.sleep_var,
            self.bounce_retrigger_var
        ))
        self.midi_thread.daemon = True
        self.midi_thread.start()
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        debug_print(f"Starting MIDI loop with input device: {in_device}")

    def stop_midi(self):
        self.stop_event.set()
        if self.midi_thread is not None:
            self.midi_thread.join()
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        global midi_out
        if midi_out:
            midi_out.close()
            midi_out = None
        debug_print("MIDI loop stopped.")

    def on_close(self):
        self.stop_midi()
        self.destroy()

if __name__ == '__main__':
    app = MidiSelectorApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
