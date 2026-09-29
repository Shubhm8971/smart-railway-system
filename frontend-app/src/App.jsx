import SeatSelection from "./components/SeatSelection";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <SeatSelection
        trainId="PASTE_TRAIN_ID_FROM_GET_TRAINS"
        userId="64b7f0c2a1b2c3d4e5f60718"
      />
    </div>
  );
}