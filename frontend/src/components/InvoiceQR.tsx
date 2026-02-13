"use client";
import { QRCodeSVG } from "qrcode.react";

interface InvoiceQRProps {
  address: string;
  amountXmr: string;
  size?: number;
}

export default function InvoiceQR({ address, amountXmr, size = 200 }: InvoiceQRProps) {
  // Build monero: URI — format: monero:<address>?tx_amount=<amount>
  const uri = `monero:${address}?tx_amount=${amountXmr}`;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="bg-white p-3 rounded-lg">
        <QRCodeSVG
          value={uri}
          size={size}
          level="M"
          bgColor="#FFFFFF"
          fgColor="#000000"
        />
      </div>
      <p className="text-xs text-gb-text-secondary text-center max-w-[240px] break-all font-mono">
        {uri}
      </p>
    </div>
  );
}
