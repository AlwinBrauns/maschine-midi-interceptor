import tkinter as tk
from tkinter import ttk, messagebox
import mido
import threading
import time
from collections import defaultdict

mido.set_backend('mido.backends.rtmidi')
midi_out = None
note_state = defaultdict(lambda: "none")

class MidiSelectorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MIDI Aftertouch -> Note-On Converter")
        self.geometry("400x450")
        self.midi_thread = None
        self.stop_event = threading.Event()
        self.pass_polytouch_var = tk.BooleanVar(value=False)
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
        self.check_polytouch = tk.Checkbutton(self, text="Pass polytouch for real/artificial notes", variable=self.pass_polytouch_var)
        self.check_polytouch.pack(pady=5)
        tk.Label(self, text="Threshold:").pack(pady=5)
        self.threshold_var = tk.IntVar(value=10)
        self.slider_thresh = tk.Scale(self, variable=self.threshold_var, from_=1, to=20, orient=tk.HORIZONTAL)
        self.slider_thresh.pack(pady=5)
        self.start_button = tk.Button(self, text="Start", command=self.start_midi)
        self.start_button.pack(pady=10)
        self.stop_button = tk.Button(self, text="Stop", command=self.stop_midi, state=tk.DISABLED)
        self.stop_button.pack(pady=5)
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
            print(f"MIDI output opened: {out_device}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open MIDI output: {e}")
            return
        self.stop_event.clear()
        self.midi_thread = threading.Thread(target=midi_loop, args=(in_device, self.stop_event, self.pass_polytouch_var, self.threshold_var))
        self.midi_thread.daemon = True
        self.midi_thread.start()
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        print(f"Starting MIDI loop with input device: {in_device}")
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
        print("MIDI loop stopped.")
    def on_close(self):
        self.stop_midi()
        self.destroy()

def handle_message(msg, pass_polytouch_var, threshold_var):
    print(f"Incoming: {msg}")
    if msg.type == 'note_on' and msg.velocity > 0:
        note_state[msg.note] = "real"
        if midi_out:
            midi_out.send(msg)
    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
        note_state[msg.note] = "none"
        if midi_out:
            midi_out.send(msg)
    elif msg.type == 'polytouch':
        current_state = note_state[msg.note]
        channel = getattr(msg, 'channel', 0)
        if current_state == "none":
            if msg.value > threshold_var.get():
                note_state[msg.note] = "artificial"
                velocity_for_artificial = min(127, msg.value)
                artificial_on = mido.Message('note_on', note=msg.note, velocity=velocity_for_artificial, channel=channel)
                print(f"Artificial Note-On: {artificial_on}")
                if midi_out:
                    midi_out.send(artificial_on)
        elif current_state == "artificial":
            if pass_polytouch_var.get():
                if midi_out:
                    midi_out.send(msg)
                print(f"Passing polytouch for artificial note {msg.note} (value={msg.value})")
            else:
                if msg.value < threshold_var.get():
                    note_state[msg.note] = "none"
                    artificial_off = mido.Message('note_off', note=msg.note, velocity=0, channel=channel)
                    print(f"Artificial Note-Off: {artificial_off}")
                    if midi_out:
                        midi_out.send(artificial_off)
        elif current_state == "real":
            if pass_polytouch_var.get():
                if midi_out:
                    midi_out.send(msg)
                print(f"Passing polytouch for real note {msg.note} (value={msg.value})")
            else:
                print(f"Ignoring polytouch for real note {msg.note}")

def midi_loop(inport_name, stop_event, pass_polytouch_var, threshold_var):
    try:
        with mido.open_input(inport_name) as inport:
            print("MIDI input opened:", inport_name)
            while not stop_event.is_set():
                for msg in inport.iter_pending():
                    handle_message(msg, pass_polytouch_var, threshold_var)
                time.sleep(0.01)
    except Exception as e:
        print("Error in MIDI loop:", e)

if __name__ == '__main__':
    app = MidiSelectorApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
