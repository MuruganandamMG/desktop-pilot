param([switch]$Probe, [switch]$SelfTest)
$ErrorActionPreference = 'Stop'
try {
Add-Type -AssemblyName System.Speech
Add-Type -ReferencedAssemblies System.Speech -TypeDefinition @'
using System;
using System.IO;
using System.Speech.Recognition;
using System.Speech.Synthesis;

public static class PilotSpeech {
    public static void Probe() {
        if (SpeechRecognitionEngine.InstalledRecognizers().Count == 0)
            throw new InvalidOperationException();
        using (var voice = new SpeechSynthesizer()) {
            if (voice.GetInstalledVoices().Count == 0) throw new InvalidOperationException();
        }
        Console.WriteLine("ready");
    }
    private static SpeechRecognitionEngine Recognizer() {
        RecognizerInfo selected = null;
        foreach (var info in SpeechRecognitionEngine.InstalledRecognizers())
            if (info.Culture.TwoLetterISOLanguageName == "en") { selected = info; break; }
        if (selected == null) throw new InvalidOperationException();
        var engine = new SpeechRecognitionEngine(selected);
            var builder = new GrammarBuilder();
            builder.Culture = selected.Culture;
            builder.Append(new Choices("pilot pause", "pilot resume", "pilot exit"));
            engine.LoadGrammar(new Grammar(builder));
        return engine;
    }
    public static void SelfTest() {
        using (var engine = Recognizer())
        using (var voice = new SpeechSynthesizer()) {
            foreach (var phrase in new [] { "pilot pause", "pilot resume", "pilot exit" }) {
                using (var wave = new MemoryStream()) {
                    voice.SetOutputToWaveStream(wave);
                    voice.Speak(phrase);
                    voice.SetOutputToNull();
                    wave.Position = 0;
                    engine.SetInputToWaveStream(wave);
                    var result = engine.Recognize(TimeSpan.FromSeconds(5));
                    if (result == null || result.Text != phrase || result.Confidence < 0.80)
                        throw new InvalidOperationException("Speech self-test failed");
                    engine.SetInputToNull();
                }
            }
        }
        Console.WriteLine("selftest-passed");
    }
    public static void Run() {
        using (var engine = Recognizer())
        using (var voice = new SpeechSynthesizer()) {
            engine.SpeechRecognized += delegate(object sender, SpeechRecognizedEventArgs e) {
                if (e.Result.Confidence < 0.80) return;
                switch (e.Result.Text.ToLowerInvariant()) {
                    case "pilot pause": Console.WriteLine("pause"); break;
                    case "pilot resume": Console.WriteLine("resume"); break;
                    case "pilot exit": Console.WriteLine("exit"); break;
                }
            };
            bool closing = false;
            engine.RecognizeCompleted += delegate {
                if (!closing) Console.WriteLine("error");
            };
            engine.SetInputToDefaultAudioDevice();
            engine.RecognizeAsync(RecognizeMode.Multiple);
            Console.WriteLine("ready");
            string command;
            while ((command = Console.ReadLine()) != null && command != "shutdown") {
                switch (command) {
                    case "listening": voice.Speak("I'm listening. Ask me anything."); break;
                    case "paused": voice.Speak("Paused. Questions are no longer sent to Google. Local voice controls are still listening."); break;
                    case "resumed": voice.Speak("Resuming our conversation."); break;
                    case "goodbye": voice.Speak("Goodbye."); break;
                    case "failed": voice.Speak("The voice connection stopped. Please check the terminal error. I'm waiting."); break;
                    case "limit": voice.Speak("This conversation session has ended. I'm waiting."); break;
                }
            }
            closing = true;
            engine.RecognizeAsyncCancel();
        }
    }
}
'@
if ($Probe) { [PilotSpeech]::Probe() }
elseif ($SelfTest) { [PilotSpeech]::SelfTest() }
else { [PilotSpeech]::Run() }
} catch { [Console]::WriteLine('error'); exit 1 }
