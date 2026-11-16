<?php

namespace Tests\Feature;

use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class DetectionTest extends TestCase
{
    private function leaf()
    {
        return UploadedFile::fake()->createWithContent('leaf.png', base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='));
    }

    public function test_valid_prediction_is_displayed(): void
    {
        $match = ['label' => 'Tomato___Early_blight', 'display_label' => 'Tomato - Early blight',
            'crop' => 'Tomato', 'disease' => 'Early blight', 'confidence' => .85];
        Http::fake(['*/predict' => Http::response([...$match, 'uncertain' => false, 'selected_crop' => 'tomato',
            'top_predictions' => [$match, [...$match, 'confidence' => .10], [...$match, 'confidence' => .05]]])]);
        $this->from('/')->post('/detect', ['crop' => 'tomato', 'image' => $this->leaf()])->assertRedirect('/')->assertSessionHas('prediction');
        $this->get('/')->assertSee('Early blight')->assertSee('85.0');
        Http::assertSent(fn ($request) => str_ends_with($request->url(), '/predict') && $request->hasFile('file') && collect($request->data())->contains(fn ($part) => $part['name'] === 'crop' && $part['contents'] === 'tomato'));
    }

    public function test_model_failure_is_not_reported_as_untrained(): void
    {
        Http::fake(['*/predict' => Http::response(['detail' => 'Unavailable'], 503)]);
        $this->from('/')->post('/detect', ['crop' => 'tomato', 'image' => $this->leaf()])->assertSessionHasErrors('image');
        $this->get('/')->assertSee('still initializing or could not load')->assertDontSee('not trained');
    }

    public function test_malformed_result_is_rejected(): void
    {
        Http::fake(['*/predict' => Http::response(['label' => 'invalid'])]);
        $this->from('/')->post('/detect', ['crop' => 'tomato', 'image' => $this->leaf()])->assertSessionHasErrors('image')->assertSessionMissing('prediction');
    }

    public function test_health_reports_loading(): void
    {
        Http::fake(['*/health' => Http::response(['status' => 'loading'])]);
        $this->getJson('/detect/health')->assertOk()->assertJson(['status' => 'loading']);
    }

    public function test_invalid_upload_never_reaches_ai(): void
    {
        Http::fake();
        $this->post('/detect', ['crop' => 'tomato', 'image' => UploadedFile::fake()->create('document.txt')])->assertSessionHasErrors('image');
        Http::assertNothingSent();
    }

    public function test_crop_is_required_and_cassava_is_unavailable(): void
    {
        Http::fake();
        foreach ([null, 'potato', 'cassava'] as $crop) {
            $this->from('/')->post('/detect', ['crop' => $crop, 'image' => $this->leaf()])->assertSessionHasErrors('crop');
        }
        Http::assertNothingSent();
    }

    public function test_pepper_accepts_only_two_supported_matches(): void
    {
        $match = ['label' => 'Pepper,_bell___healthy', 'display_label' => 'Pepper, bell - Healthy',
            'crop' => 'Pepper, bell', 'disease' => 'Healthy', 'confidence' => .8];
        Http::fake(['*/predict' => Http::response([...$match, 'uncertain' => false, 'selected_crop' => 'pepper',
            'top_predictions' => [$match, [...$match, 'label' => 'Pepper,_bell___Bacterial_spot', 'confidence' => .1]]])]);
        $this->from('/')->post('/detect', ['crop' => 'pepper', 'image' => $this->leaf()])->assertSessionHas('prediction');
        $this->get('/')->assertSee('Top 2 possible matches')->assertSee('value="pepper" selected', false);
    }

    public function test_predictions_for_another_crop_are_rejected(): void
    {
        $match = ['label' => 'Potato___Early_blight', 'display_label' => 'Potato - Early blight',
            'crop' => 'Potato', 'disease' => 'Early blight', 'confidence' => .85];
        Http::fake(['*/predict' => Http::response([...$match, 'uncertain' => false, 'selected_crop' => 'tomato',
            'top_predictions' => [$match]])]);
        $this->from('/')->post('/detect', ['crop' => 'tomato', 'image' => $this->leaf()])->assertSessionHasErrors('image')->assertSessionMissing('prediction');
    }

    public function test_weak_crop_match_is_presented_as_unconfirmed(): void
    {
        $match = ['label' => 'Tomato___Early_blight', 'display_label' => 'Tomato - Early blight',
            'crop' => 'Tomato', 'disease' => 'Early blight', 'confidence' => .00086958];
        Http::fake(['*/predict' => Http::response([...$match, 'uncertain' => true, 'selected_crop' => 'tomato',
            'uncertainty_reason' => 'crop_conflict', 'top_predictions' => [$match]])]);
        $this->from('/')->post('/detect', ['crop' => 'tomato', 'image' => $this->leaf()])->assertSessionHas('prediction');
        $this->get('/')->assertSee('Unable to identify confidently')->assertSee('0.09')
            ->assertSee('tentative matches, not a diagnosis')->assertSee('outside your selected crop')
            ->assertDontSee('Pepper has two supported classes.');
    }
}
